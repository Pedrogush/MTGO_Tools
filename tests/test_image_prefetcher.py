"""Tests for the predictive card-image prefetcher (issue #951)."""

from __future__ import annotations

import threading
import time

from services.image_service.prefetcher import ImagePrefetcher
from services.image_service.priorities import (
    PRIORITY_BACKGROUND,
    PRIORITY_RESEARCH_VISIBLE,
    PRIORITY_SELECTED_DECK,
)


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
    prefetcher = _stopped_prefetcher(lambda req, prio: requests.append(req) or True)

    prefetcher._run_batch("deck", lambda: ["Lightning Bolt", "Ponder"])

    assert [req.card_name for req in requests] == ["Lightning Bolt", "Ponder"]
    assert all(req.size == "normal" for req in requests)
    assert all(req.uuid is None and req.set_code is None for req in requests)


def test_run_batch_caps_at_batch_limit():
    requests = []
    prefetcher = _stopped_prefetcher(lambda req, prio: requests.append(req) or True, batch_limit=5)

    prefetcher._run_batch("search", lambda: [f"Card {i}" for i in range(50)])

    assert len(requests) == 5


def test_run_batch_dedupes_within_and_across_batches():
    requests = []
    prefetcher = _stopped_prefetcher(lambda req, prio: requests.append(req) or True)

    prefetcher._run_batch("deck", lambda: ["Ponder", "ponder", "  Ponder  ", "Opt"])
    assert [req.card_name for req in requests] == ["Ponder", "Opt"]

    # A later batch (any source) skips names already fed to the queue.
    prefetcher._run_batch("search", lambda: ["Ponder", "Brainstorm"])
    assert [req.card_name for req in requests] == ["Ponder", "Opt", "Brainstorm"]


def test_run_batch_skips_blank_names_and_tolerates_provider_errors():
    requests = []
    prefetcher = _stopped_prefetcher(lambda req, prio: requests.append(req) or True)

    prefetcher._run_batch("deck", lambda: ["", "   ", None, "Opt"])
    assert [req.card_name for req in requests] == ["Opt"]

    def _boom():
        raise RuntimeError("provider failed")

    prefetcher._run_batch("deck", _boom)  # must not raise
    assert len(requests) == 1


def test_run_batch_tolerates_enqueue_errors():
    calls = []

    def _enqueue(request, priority):
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

    def _enqueue(request, priority):
        requests.append(request)
        if len(requests) == 2:
            done.set()
        return True

    prefetcher = ImagePrefetcher(_enqueue, start_delay=0.0)
    try:
        prefetcher.prefetch("deck", ["Lightning Bolt", "Ponder"])
        assert done.wait(timeout=5.0), "prefetch batch never ran"
    finally:
        prefetcher.stop()
    assert sorted(req.card_name for req in requests) == ["Lightning Bolt", "Ponder"]


def test_background_batches_idle_through_start_delay_and_stop_interrupts_it():
    requests = []
    prefetcher = ImagePrefetcher(lambda req, prio: requests.append(req) or True, start_delay=60.0)
    try:
        prefetcher.prefetch("warmup", ["Lightning Bolt"], priority=PRIORITY_BACKGROUND)
        time.sleep(0.2)
        # Still inside the start delay: the background submission is held.
        assert requests == []
        with prefetcher._condition:
            assert "warmup" in prefetcher._pending
    finally:
        started = time.monotonic()
        prefetcher.stop()
        # stop() must interrupt the start delay rather than wait it out.
        assert time.monotonic() - started < 5.0


def test_user_driven_batch_bypasses_start_delay():
    """A selected-deck batch must run immediately, even during the delay."""
    done = threading.Event()
    prefetcher = ImagePrefetcher(lambda req, prio: done.set() or True, start_delay=60.0)
    try:
        prefetcher.prefetch("deck", ["Lightning Bolt"], priority=PRIORITY_SELECTED_DECK)
        assert done.wait(timeout=5.0), "user-driven batch was held by the start delay"
    finally:
        prefetcher.stop()


def test_most_urgent_pending_source_runs_first():
    """With several sources pending, the lowest-priority-value one runs first."""
    order = []
    prefetcher = _stopped_prefetcher(lambda req, prio: order.append((req.card_name, prio)) or True)
    prefetcher._background_deadline = 0.0  # grace delay already elapsed
    with prefetcher._condition:
        prefetcher.prefetch("search", ["Opt"], priority=PRIORITY_RESEARCH_VISIBLE)
        prefetcher.prefetch("deck", ["Ponder"], priority=PRIORITY_SELECTED_DECK)
    for _ in range(2):
        with prefetcher._condition:
            source, (priority, provider, on_batch) = prefetcher._next_batch_locked()
        prefetcher._run_batch(source, provider, priority=priority, on_batch=on_batch)
    assert order == [("Ponder", PRIORITY_SELECTED_DECK), ("Opt", PRIORITY_RESEARCH_VISIBLE)]


def test_submitted_name_resubmitted_at_better_tier_only():
    """A name fed at a background tier re-enqueues at a better tier (promotion),
    but never again at the same or a worse tier."""
    calls = []
    prefetcher = _stopped_prefetcher(lambda req, prio: calls.append((req.card_name, prio)) or True)

    prefetcher._run_batch("warmup", lambda: ["Ponder"], priority=PRIORITY_BACKGROUND)
    prefetcher._run_batch("warmup", lambda: ["Ponder"], priority=PRIORITY_BACKGROUND)
    prefetcher._run_batch("deck", lambda: ["Ponder"], priority=PRIORITY_SELECTED_DECK)
    prefetcher._run_batch("deck", lambda: ["Ponder"], priority=PRIORITY_SELECTED_DECK)

    assert calls == [
        ("Ponder", PRIORITY_BACKGROUND),
        ("Ponder", PRIORITY_SELECTED_DECK),
    ]


def test_on_batch_reports_enqueued_and_skipped():
    outcomes = []
    prefetcher = _stopped_prefetcher(lambda req, prio: req.card_name == "Ponder")

    prefetcher._run_batch(
        "deck",
        lambda: ["Ponder", "Opt"],
        priority=PRIORITY_SELECTED_DECK,
        on_batch=lambda source, enqueued, skipped: outcomes.append((source, enqueued, skipped)),
    )

    assert outcomes == [("deck", ["Ponder"], ["Opt"])]


def test_prefetch_after_stop_is_a_noop():
    requests = []
    prefetcher = ImagePrefetcher(lambda req, prio: requests.append(req) or True)
    prefetcher.stop()

    prefetcher.prefetch("deck", ["Lightning Bolt"])

    with prefetcher._condition:
        assert not prefetcher._pending
    assert requests == []
