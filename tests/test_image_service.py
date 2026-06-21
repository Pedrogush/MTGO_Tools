"""Tests for ImageService business logic."""

import threading
import time

import pytest

import services.image_service as image_service
from services.image_service import CardImageDownloadQueue, CardImageRequest, ImageService
from utils.constants.timing import (
    IMAGE_DOWNLOAD_INITIAL_BACKOFF_SECONDS,
    IMAGE_DOWNLOAD_MAX_RETRIES,
    IMAGE_DOWNLOAD_SLOW_THRESHOLD_SECONDS,
)


@pytest.fixture(autouse=True)
def synchronous_call_after(monkeypatch):
    """Run ``wx.CallAfter`` synchronously when wx is importable.

    ``import wx`` succeeds on the Windows CI runner but there is no ``wx.App``
    in the test process, so a real ``wx.CallAfter(...)`` raises
    ``AssertionError: No wx.App created yet``. Off-Windows (WSL dev) wx is
    absent and ``ImageCacheMixin._call_after`` already falls back to a direct
    call. Stubbing here keeps the dispatch tests passing in both places.
    """
    try:
        import wx
    except ImportError:
        return  # off-Windows: production fallback already runs synchronously
    monkeypatch.setattr(wx, "CallAfter", lambda func, *a, **k: func(*a, **k))


@pytest.fixture(autouse=True)
def reset_not_found_keys():
    """Clear the class-level not-found cache around each test.

    ``CardImageDownloadQueue._NOT_FOUND_KEYS`` is shared by every instance, so
    a test that marks a key not-found would otherwise leak that state into
    sibling tests and silently change enqueue()/selected-priority behaviour.
    """
    CardImageDownloadQueue._NOT_FOUND_KEYS.clear()
    yield
    CardImageDownloadQueue._NOT_FOUND_KEYS.clear()


@pytest.fixture
def image_service_instance():
    """Provide an ImageService and guarantee its background thread is stopped.

    ``ImageService.__init__`` spins up a daemon thread and a ThreadPoolExecutor
    via ``CardImageDownloadQueue``. Without an explicit ``shutdown()`` those
    leak across the suite (the exact leaked-daemon-thread scenario that has
    crashed CI at interpreter shutdown).
    """
    service = ImageService()
    try:
        yield service
    finally:
        service.shutdown()


def test_image_service_initialization(image_service_instance):
    """Test ImageService initializes with correct default state."""
    service = image_service_instance

    assert service.bulk_data_by_name is None
    assert service.printing_index_loading is False
    assert service.image_downloader is None


def test_set_bulk_data(image_service_instance):
    """Test setting bulk data."""
    service = image_service_instance
    test_data = {
        "Lightning Bolt": [{"name": "Lightning Bolt", "set": "LEA"}],
        "Island": [{"name": "Island", "set": "LEA"}],
    }

    service.set_bulk_data(test_data)

    assert service.get_bulk_data() == test_data


def test_get_bulk_data_initially_none(image_service_instance):
    """Test that bulk data is initially None."""
    service = image_service_instance

    assert service.get_bulk_data() is None


def test_clear_printing_index_loading(image_service_instance):
    """Test clearing the printing index loading flag."""
    service = image_service_instance
    service.printing_index_loading = True

    service.clear_printing_index_loading()

    assert service.printing_index_loading is False


def test_is_loading_initially_false(image_service_instance):
    """Test that loading flag is initially false."""
    service = image_service_instance

    assert service.is_loading() is False


def test_is_loading_when_loading(image_service_instance):
    """Test that is_loading returns True when loading."""
    service = image_service_instance
    service.printing_index_loading = True

    assert service.is_loading() is True


class _FakeCache:
    def __init__(self, cached_keys=None):
        # Set of (card_name, set_code, size) / (card_name, size) tuples to
        # report as already cached.
        self._cached_keys = set(cached_keys or ())

    def get_image_path_for_printing(self, card_name, set_code, size):
        if (card_name, set_code, size) in self._cached_keys:
            return "path"
        return None

    def get_image_path(self, card_name, size):
        if (card_name, size) in self._cached_keys:
            return "path"
        return None


class _FakeDownloader:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0

    def download_card_image_by_name(self, name, size, set_code=None):
        self.calls += 1
        response = self._responses[self.calls - 1]
        if isinstance(response, Exception):
            raise response
        return response


def _build_queue(downloader=None, *, on_failed=None, cache=None):
    queue = CardImageDownloadQueue(cache or _FakeCache(), on_failed=on_failed)
    if downloader is not None:
        queue._downloader = downloader
    return queue


def _request(**overrides):
    params = {
        "card_name": "Mirrorpool",
        "uuid": None,
        "set_code": "aeoe",
        "collector_number": None,
        "size": "normal",
    }
    params.update(overrides)
    return CardImageRequest(**params)


def test_download_request_retries_with_backoff(monkeypatch):
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    downloader = _FakeDownloader([(False, "429 Too Many Requests"), (True, "ok")])
    queue = _build_queue(downloader)
    sleeps = []
    # Capture backoff durations without actually waiting; the queue now uses
    # the stop event's wait() so it can be interrupted on shutdown.
    monkeypatch.setattr(queue._stop_event, "wait", lambda seconds: sleeps.append(seconds) or False)
    try:
        assert queue._download_request(_request()) is True
    finally:
        queue.stop()

    assert downloader.calls == 2
    assert sleeps == [0.5]


def test_download_request_stop_event_interrupts_backoff(monkeypatch):
    """Setting the stop event during backoff should abort retries promptly."""
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    downloader = _FakeDownloader([(False, "429 Too Many Requests"), (True, "ok")])
    queue = _build_queue(downloader)
    waits = []

    def fake_wait(seconds):
        waits.append(seconds)
        # Simulate shutdown happening during the backoff sleep.
        queue._stop_event.set()
        return True

    monkeypatch.setattr(queue._stop_event, "wait", fake_wait)
    try:
        # Should return False (giving up) instead of retrying after the wait
        # was interrupted by the stop event.
        assert queue._download_request(_request()) is False
    finally:
        queue.stop()

    # Downloader was only called once; the retry loop bailed out after the
    # interrupted backoff instead of issuing a second request.
    assert downloader.calls == 1
    assert waits == [0.5]


def test_download_request_stop_event_skips_first_attempt():
    """If stop is already signaled, the download loop should exit immediately."""
    downloader = _FakeDownloader([(True, "ok")])
    queue = _build_queue(downloader)
    queue._stop_event.set()
    try:
        assert queue._download_request(_request()) is False
    finally:
        queue.stop()
    assert downloader.calls == 0


def test_download_request_404_no_retry(monkeypatch):
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    failed = []
    downloader = _FakeDownloader(
        [Exception("404 Client Error: Not Found for url: https://api.scryfall.com/cards")]
    )
    queue = _build_queue(downloader, on_failed=lambda request, msg: failed.append((request, msg)))
    waits = []
    # A permanent failure must skip the retry/backoff path entirely. The retry
    # path waits on the stop event, so prove no backoff occurred by asserting
    # _stop_event.wait() is never invoked (mirroring the retry tests).
    monkeypatch.setattr(queue._stop_event, "wait", lambda seconds: waits.append(seconds) or False)
    try:
        request = _request()
        assert queue._download_request(request) is False
        # The not-found key is now recorded, so further enqueues are skipped.
        assert queue.enqueue(request) is False
        assert queue.enqueue(_request(size="large")) is False
        assert queue.enqueue(_request(collector_number="42")) is False
    finally:
        queue.stop()

    assert downloader.calls == 1
    assert waits == []
    assert len(failed) == 1


@pytest.mark.parametrize(
    "message",
    [
        "404 Client Error: Not Found for url: x",
        "No uuid for Mirrorpool",
        "missing uuid for multi-face card",
        "no downloadable faces",
        "no normal image for Mirrorpool",
        "no small image for Mirrorpool",
        "no large image for Mirrorpool",
        "no png image for Mirrorpool",
        "no border_crop image for Mirrorpool",
        "no art_crop image for Mirrorpool",
    ],
)
def test_is_permanent_failure_message_true(message):
    assert CardImageDownloadQueue._is_permanent_failure_message(message) is True


@pytest.mark.parametrize(
    "message",
    [
        "",
        "429 Too Many Requests",
        "Connection reset by peer",
        "404 but the body says ok",  # 404 without "not found" is transient
    ],
)
def test_is_permanent_failure_message_false(message):
    assert CardImageDownloadQueue._is_permanent_failure_message(message) is False


def test_download_request_permanent_marker_bails_without_retry(monkeypatch):
    """A non-404 permanent marker should fail immediately without backoff."""
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    failed = []
    downloader = _FakeDownloader([(False, "no normal image for Mirrorpool")])
    queue = _build_queue(downloader, on_failed=lambda request, msg: failed.append((request, msg)))
    waits = []
    monkeypatch.setattr(queue._stop_event, "wait", lambda seconds: waits.append(seconds) or False)
    try:
        request = _request()
        assert queue._download_request(request) is False
        # The permanent failure was recorded as not-found, blocking re-enqueue.
        assert queue.enqueue(request) is False
    finally:
        queue.stop()

    assert downloader.calls == 1
    assert waits == []
    assert len(failed) == 1


def test_download_request_slow_success_treated_as_failure(monkeypatch):
    """A 'success' that is too slow and never landed on disk is rejected."""
    # monotonic advances past the slow threshold between the two reads.
    times = iter([0.0, IMAGE_DOWNLOAD_SLOW_THRESHOLD_SECONDS + 1.0])
    monkeypatch.setattr(image_service.time, "monotonic", lambda: next(times))
    downloader = _FakeDownloader([(True, "ok")])
    # _FakeCache reports nothing cached, so the slow success cannot be verified.
    queue = _build_queue(downloader)
    try:
        assert queue._download_request(_request()) is False
    finally:
        queue.stop()
    assert downloader.calls == 1


def test_enqueue_fresh_request_returns_true():
    queue = _build_queue()
    try:
        request = _request()
        assert queue.enqueue(request) is True
        with queue._condition:
            assert request.queue_key() in queue._pending_keys
            assert request in queue._queue
    finally:
        queue.stop()


def test_enqueue_duplicate_returns_false():
    queue = _build_queue()
    try:
        request = _request()
        assert queue.enqueue(request) is True
        assert queue.enqueue(_request()) is False
        with queue._condition:
            # Still exactly one copy queued.
            assert list(queue._queue).count(request) == 1
    finally:
        queue.stop()


def test_enqueue_not_fetchable_returns_false():
    queue = _build_queue()
    try:
        assert queue.enqueue(_request(card_name="   ")) is False
    finally:
        queue.stop()


def test_enqueue_already_cached_returns_false():
    cache = _FakeCache(cached_keys={("Mirrorpool", "aeoe", "normal")})
    queue = _build_queue(cache=cache)
    try:
        assert queue.enqueue(_request()) is False
        with queue._condition:
            assert len(queue._queue) == 0
    finally:
        queue.stop()


def test_enqueue_prioritize_front_loads_and_dedups():
    queue = _build_queue()
    try:
        first = _request(set_code="aaa")
        second = _request(set_code="bbb")
        assert queue.enqueue(first) is True
        assert queue.enqueue(second) is True
        # Re-enqueueing `first` with prioritize=True should move it to the
        # front without leaving a duplicate behind.
        assert queue.enqueue(_request(set_code="aaa"), prioritize=True) is True
        with queue._condition:
            assert queue._queue[0].queue_key() == first.queue_key()
            assert list(queue._queue).count(first) == 1
            assert len(queue._queue) == 2
    finally:
        queue.stop()


def test_set_selected_request_promotes_to_front():
    """A fresh selected request is promoted to the front of the queue."""
    queue = _build_queue()
    try:
        # Stop the worker thread so it cannot drain the queue mid-assert.
        queue.stop()
        other = _request(set_code="aaa")
        queue.enqueue(other)
        selected = _request(set_code="bbb")
        queue.set_selected_request(selected)
        with queue._condition:
            assert queue._queue[0].queue_key() == selected.queue_key()
            assert selected.queue_key() in queue._pending_keys
    finally:
        queue.stop()


def test_set_selected_request_moves_pending_to_front():
    """A selected request already pending is moved to the front (no dup)."""
    queue = _build_queue()
    try:
        queue.stop()
        first = _request(set_code="aaa")
        selected = _request(set_code="bbb")
        queue.enqueue(first)
        queue.enqueue(selected)
        queue.set_selected_request(selected)
        with queue._condition:
            assert queue._queue[0].queue_key() == selected.queue_key()
            assert list(queue._queue).count(selected) == 1
            assert len(queue._queue) == 2
    finally:
        queue.stop()


def test_selected_request_skips_not_found():
    downloader = _FakeDownloader([(False, "nope")])
    queue = _build_queue(downloader)
    request = _request()
    not_found_key = queue._not_found_key(request)
    try:
        queue.stop()
        queue._add_not_found_key(not_found_key)
        queue.set_selected_request(request)
        with queue._condition:
            assert request.queue_key() not in queue._pending_keys
            assert request.queue_key() not in queue._inflight_keys
            assert request not in queue._queue
    finally:
        queue._discard_not_found_key(not_found_key)


def test_download_request_cached_returns_true_without_downloading():
    """An already-cached request short-circuits before hitting the downloader."""
    cache = _FakeCache(cached_keys={("Mirrorpool", "aeoe", "normal")})
    downloader = _FakeDownloader([])
    queue = _build_queue(downloader, cache=cache)
    try:
        queue.stop()
        assert queue._download_request(_request()) is True
    finally:
        queue.stop()
    # The cache hit means the downloader was never consulted.
    assert downloader.calls == 0


def test_download_request_success_clears_prior_not_found(monkeypatch):
    """A fresh, fast success removes a stale not-found marker so re-enqueue works."""
    # Constant monotonic => zero elapsed, so the slow-success guard is skipped
    # and the success branch (which discards the not-found key) is reached.
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    # Empty cache: the cached short-circuit is NOT taken, exercising the real
    # download + success path rather than the early return.
    downloader = _FakeDownloader([(True, "ok")])
    queue = _build_queue(downloader)
    request = _request()
    not_found_key = queue._not_found_key(request)
    try:
        queue._add_not_found_key(not_found_key)
        assert queue._download_request(request) is True
        assert queue._is_not_found_key_blocked(not_found_key) is False
    finally:
        queue._discard_not_found_key(not_found_key)
        queue.stop()
    assert downloader.calls == 1


def test_download_request_retries_exhausted_returns_false(monkeypatch):
    """Backoff doubles each attempt and a final failure gives up cleanly."""
    monkeypatch.setattr(image_service.time, "monotonic", lambda: 0.0)
    # All attempts are transient failures (initial + IMAGE_DOWNLOAD_MAX_RETRIES).
    responses = [(False, "429 Too Many Requests")] * (IMAGE_DOWNLOAD_MAX_RETRIES + 1)
    downloader = _FakeDownloader(responses)
    queue = _build_queue(downloader)
    sleeps = []
    monkeypatch.setattr(queue._stop_event, "wait", lambda seconds: sleeps.append(seconds) or False)
    try:
        assert queue._download_request(_request()) is False
    finally:
        queue.stop()

    assert downloader.calls == IMAGE_DOWNLOAD_MAX_RETRIES + 1
    # Backoff doubles between retries: 0.5, 1.0, 2.0, ... for MAX_RETRIES waits.
    expected = [
        IMAGE_DOWNLOAD_INITIAL_BACKOFF_SECONDS * (2**i) for i in range(IMAGE_DOWNLOAD_MAX_RETRIES)
    ]
    assert sleeps == expected


def test_notify_downloaded_fires_only_when_cached():
    """_notify_downloaded invokes the callback iff the image landed in cache."""
    cache = _FakeCache(cached_keys={("Mirrorpool", "aeoe", "normal")})
    downloaded = []
    queue = CardImageDownloadQueue(cache, on_downloaded=downloaded.append)
    try:
        queue.stop()
        cached_request = _request()
        queue._notify_downloaded(cached_request)
        assert downloaded == [cached_request]

        downloaded.clear()
        # A request the cache does not report should not notify.
        uncached_request = _request(set_code="zzz")
        queue._notify_downloaded(uncached_request)
        assert downloaded == []
    finally:
        queue.stop()


def test_request_queue_key_uses_uuid_when_present():
    """queue_key keys off the uuid (ignoring set/collector) when one is set."""
    with_uuid = _request(uuid="ABC-123", set_code="aaa", collector_number="7")
    other_set = _request(uuid="ABC-123", set_code="bbb", collector_number="9")
    # Same uuid + size collapse to the same key regardless of set/collector.
    assert with_uuid.queue_key() == ("uuid", "abc-123", "normal", "")
    assert with_uuid.queue_key() == other_set.queue_key()
    # A differing size yields a distinct key.
    assert _request(uuid="ABC-123", size="large").queue_key() != with_uuid.queue_key()


def test_image_service_download_callback_dispatched(image_service_instance):
    """A queued success dispatches the registered download callback via _call_after."""
    service = image_service_instance
    received = []
    service.set_image_download_callback(received.append)

    request = _request()
    # Drive the success path directly: _handle_image_downloaded routes through
    # _call_after (wx.CallAfter when wx is importable, direct call otherwise).
    service._handle_image_downloaded(request)

    assert received == [request]


def test_image_service_download_callback_noop_without_callback(image_service_instance):
    """With no callback registered, dispatch is a silent no-op."""
    service = image_service_instance
    # No set_image_download_callback call; must not raise.
    service._handle_image_downloaded(_request())


def test_image_service_failed_callback_dispatched(image_service_instance):
    """A failure dispatches the registered failed callback with the message."""
    service = image_service_instance
    received = []
    service.set_image_download_failed_callback(lambda req, msg: received.append((req, msg)))

    request = _request()
    service._handle_image_download_failed(request, "404 not found")

    assert received == [(request, "404 not found")]


def test_image_service_failed_callback_noop_without_callback(image_service_instance):
    """With no failed-callback registered, dispatch is a silent no-op."""
    service = image_service_instance
    service._handle_image_download_failed(_request(), "boom")


def test_image_service_callbacks_can_be_cleared(image_service_instance):
    """Passing None clears a previously-registered callback."""
    service = image_service_instance
    received = []
    service.set_image_download_callback(received.append)
    service.set_image_download_callback(None)

    service._handle_image_downloaded(_request())
    assert received == []


def test_queue_card_image_download_delegates_to_queue(image_service_instance, monkeypatch):
    """queue_card_image_download forwards to the queue and returns its result."""
    service = image_service_instance
    calls = []

    def fake_enqueue(request, *, prioritize):
        calls.append((request, prioritize))
        return True

    monkeypatch.setattr(service._download_queue, "enqueue", fake_enqueue)
    request = _request()

    assert service.queue_card_image_download(request, prioritize=True) is True
    assert calls == [(request, True)]


def test_queue_card_image_download_returns_false_when_skipped(image_service_instance, monkeypatch):
    """A skipped enqueue (e.g. already cached) propagates False to the caller."""
    service = image_service_instance
    monkeypatch.setattr(service._download_queue, "enqueue", lambda request, *, prioritize: False)

    assert service.queue_card_image_download(_request(), prioritize=False) is False


def test_set_selected_card_request_delegates_to_queue(image_service_instance, monkeypatch):
    """set_selected_card_request forwards the request to the queue unchanged."""
    service = image_service_instance
    received = []
    monkeypatch.setattr(service._download_queue, "set_selected_request", received.append)
    request = _request()

    service.set_selected_card_request(request)
    assert received == [request]

    received.clear()
    service.set_selected_card_request(None)
    assert received == [None]


def test_enqueue_already_inflight_returns_false():
    """An enqueue whose key is already in flight is rejected without queueing."""
    queue = _build_queue()
    try:
        queue.stop()
        request = _request()
        with queue._condition:
            queue._inflight_keys.add(request.queue_key())
        assert queue.enqueue(request) is False
        with queue._condition:
            assert len(queue._queue) == 0
            assert request.queue_key() not in queue._pending_keys
    finally:
        queue.stop()


def test_ensure_selected_priority_skips_already_cached():
    """A cached selected request is never queued."""
    cache = _FakeCache(cached_keys={("Mirrorpool", "aeoe", "normal")})
    queue = _build_queue(cache=cache)
    try:
        queue.stop()
        queue.set_selected_request(_request())
        with queue._condition:
            assert len(queue._queue) == 0
            assert len(queue._pending_keys) == 0
    finally:
        queue.stop()


def test_ensure_selected_priority_skips_inflight():
    """A selected request already in flight is not re-queued."""
    queue = _build_queue()
    try:
        queue.stop()
        request = _request()
        with queue._condition:
            queue._inflight_keys.add(request.queue_key())
        queue.set_selected_request(request)
        with queue._condition:
            assert request not in queue._queue
            assert request.queue_key() not in queue._pending_keys
    finally:
        queue.stop()


def test_ensure_selected_priority_skips_not_fetchable():
    """A selected request with no fetchable name is ignored."""
    queue = _build_queue()
    try:
        queue.stop()
        queue.set_selected_request(_request(card_name="   "))
        with queue._condition:
            assert len(queue._queue) == 0
            assert len(queue._pending_keys) == 0
    finally:
        queue.stop()


def test_set_selected_request_none_is_noop():
    """Clearing the selection with None queues nothing."""
    queue = _build_queue()
    try:
        queue.stop()
        queue.set_selected_request(None)
        with queue._condition:
            assert len(queue._queue) == 0
            assert len(queue._pending_keys) == 0
    finally:
        queue.stop()


def test_worker_loop_downloads_and_notifies():
    """The running worker drains the queue, downloads, and notifies on success.

    Exercises the real threaded dispatch path: ``_run`` pops the request,
    submits it to the executor, ``_download_request`` succeeds, and
    ``_handle_download_complete`` fires ``on_downloaded`` and clears the
    inflight bookkeeping.
    """
    cache = _FakeCache(cached_keys={("Mirrorpool", "aeoe", "normal")})
    downloader = _FakeDownloader([(True, "ok")])
    done = threading.Event()
    downloaded = []

    def on_downloaded(request):
        downloaded.append(request)
        done.set()

    queue = CardImageDownloadQueue(cache, on_downloaded=on_downloaded)
    queue._downloader = downloader
    try:
        request = _request()
        assert queue.enqueue(request) is True
        assert done.wait(timeout=5.0), "worker never notified completion"
        assert downloaded == [request]
        with queue._condition:
            assert request.queue_key() not in queue._inflight_keys
            assert queue._inflight_count == 0
            assert request.queue_key() not in queue._pending_keys
    finally:
        queue.stop()


def test_worker_loop_recovers_when_download_request_raises():
    """A ``_download_request`` that raises is swallowed; bookkeeping still clears.

    Drives the ``_handle_download_complete`` exception branch end to end: the
    executor future resolves to an exception, the done-callback logs and
    recovers, and the inflight counters return to zero without notifying
    ``on_downloaded``.
    """
    cache = _FakeCache()
    downloaded = []
    raised = threading.Event()
    queue = CardImageDownloadQueue(cache, on_downloaded=downloaded.append)

    def boom(request):
        raised.set()
        raise RuntimeError("boom")

    # Replace the unit of work submitted to the executor so the future's
    # result() raises, exercising the except branch in _handle_download_complete.
    queue._download_request = boom
    try:
        request = _request()
        assert queue.enqueue(request) is True
        assert raised.wait(timeout=5.0), "worker never ran the request"

        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with queue._condition:
                cleared = (
                    request.queue_key() not in queue._inflight_keys and queue._inflight_count == 0
                )
            if cleared:
                break
            queue._stop_event.wait(0.01)

        # The raising work item never lands the image in cache, so no notify.
        assert downloaded == []
        with queue._condition:
            assert request.queue_key() not in queue._inflight_keys
            assert queue._inflight_count == 0
    finally:
        queue.stop()
