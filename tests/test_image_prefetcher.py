"""Tests for the predictive card-image prefetcher (issue #951)."""

from __future__ import annotations

import threading

from services.image_service.prefetcher import ImagePrefetcher


def _stopped_prefetcher(enqueue, **kwargs) -> ImagePrefetcher:
    """Build a prefetcher with its worker thread already stopped.

    Batches are then driven synchronously through ``_run_batch`` so tests are
    deterministic (no sleeps, no cross-thread races). The stop event is
    cleared after the (dead) worker thread joins so ``_run_batch`` doesn't
    bail out of its enqueue loop.
    """
    prefetcher = ImagePrefetcher(enqueue, **kwargs)
    prefetcher.stop()
    prefetcher._stop_event.clear()
    return prefetcher


def test_run_batch_enqueues_normal_size_requests():
    requests = []
    prefetcher = _stopped_prefetcher(lambda req: requests.append(req) or True)

    prefetcher._run_batch("deck", lambda: ["Lightning Bolt", "Ponder"])

    assert [req.card_name for req in requests] == ["Lightning Bolt", "Ponder"]
    assert all(req.size == "normal" for req in requests)
    assert all(req.uuid is None and req.set_code is None for req in requests)


def test_run_batch_caps_at_batch_limit():
    requests = []
    prefetcher = _stopped_prefetcher(lambda req: requests.append(req) or True, batch_limit=5)

    prefetcher._run_batch("search", lambda: [f"Card {i}" for i in range(50)])

    assert len(requests) == 5


def test_run_batch_dedupes_within_and_across_batches():
    requests = []
    prefetcher = _stopped_prefetcher(lambda req: requests.append(req) or True)

    prefetcher._run_batch("deck", lambda: ["Ponder", "ponder", "  Ponder  ", "Opt"])
    assert [req.card_name for req in requests] == ["Ponder", "Opt"]

    # A later batch (any source) skips names already fed to the queue.
    prefetcher._run_batch("search", lambda: ["Ponder", "Brainstorm"])
    assert [req.card_name for req in requests] == ["Ponder", "Opt", "Brainstorm"]


def test_run_batch_skips_blank_names_and_tolerates_provider_errors():
    requests = []
    prefetcher = _stopped_prefetcher(lambda req: requests.append(req) or True)

    prefetcher._run_batch("deck", lambda: ["", "   ", None, "Opt"])
    assert [req.card_name for req in requests] == ["Opt"]

    def _boom():
        raise RuntimeError("provider failed")

    prefetcher._run_batch("deck", _boom)  # must not raise
    assert len(requests) == 1


def test_run_batch_tolerates_enqueue_errors():
    calls = []

    def _enqueue(request):
        calls.append(request.card_name)
        if request.card_name == "Bad Card":
            raise RuntimeError("enqueue failed")
        return True

    prefetcher = _stopped_prefetcher(_enqueue)
    prefetcher._run_batch("deck", lambda: ["Bad Card", "Opt"])
    assert calls == ["Bad Card", "Opt"]


def test_prefetch_runs_batch_on_worker_thread():
    done = threading.Event()
    requests = []

    def _enqueue(request):
        requests.append(request)
        if len(requests) == 2:
            done.set()
        return True

    prefetcher = ImagePrefetcher(_enqueue)
    try:
        prefetcher.prefetch("deck", ["Lightning Bolt", "Ponder"])
        assert done.wait(timeout=5.0), "prefetch batch never ran"
    finally:
        prefetcher.stop()
    assert sorted(req.card_name for req in requests) == ["Lightning Bolt", "Ponder"]


def test_prefetch_after_stop_is_a_noop():
    requests = []
    prefetcher = ImagePrefetcher(lambda req: requests.append(req) or True)
    prefetcher.stop()

    prefetcher.prefetch("deck", ["Lightning Bolt"])

    with prefetcher._condition:
        assert not prefetcher._pending
    assert requests == []
