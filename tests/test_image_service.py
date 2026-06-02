"""Tests for ImageService business logic."""

import pytest

import services.image_service as image_service
from services.image_service import CardImageDownloadQueue, CardImageRequest, ImageService
from utils.constants.timing import IMAGE_DOWNLOAD_SLOW_THRESHOLD_SECONDS


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
