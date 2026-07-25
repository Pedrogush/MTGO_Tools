"""Tests for the debounced Scryfall batch resolver (cold-start metadata).

Window grouping is made deterministic by gating the resolver's debounce sleep on
an :class:`threading.Event`: worker threads register into the pending window
while the window thread is parked in ``sleep``, then the test releases it. This
removes any dependence on wall-clock scheduling for "these landed in one batch".
"""

from __future__ import annotations

import threading
import time

import pytest

import services.image_service.batch_resolver as batch_resolver
from services.image_service.batch_resolver import ScryfallBatchResolver
from utils.constants import timing


class _FakeResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


class _RecordingSession:
    """Records /cards/collection POSTs and returns canned card data."""

    def __init__(self, cards: list[dict]) -> None:
        self._by_name = {c["name"].lower(): c for c in cards}
        self._by_id = {c["id"].lower(): c for c in cards if c.get("id")}
        self.post_calls: list[list[dict]] = []

    def post(self, url, json, timeout):  # noqa: A002 - mirror requests' signature
        identifiers = json["identifiers"]
        self.post_calls.append(identifiers)
        data = []
        for ident in identifiers:
            if "id" in ident and ident["id"].lower() in self._by_id:
                data.append(self._by_id[ident["id"].lower()])
            elif "name" in ident and ident["name"].lower() in self._by_name:
                data.append(self._by_name[ident["name"].lower()])
        return _FakeResponse({"data": data, "not_found": []})


def _card(name, uuid, set_code="set", faces=None):
    card = {"name": name, "id": uuid, "set": set_code, "collector_number": "1"}
    if faces:
        card["card_faces"] = [{"name": f} for f in faces]
    return card


@pytest.fixture
def gated_window(monkeypatch):
    """Freeze the resolver's debounce sleep until the test releases it.

    Returns a callable ``run(resolver, names)`` that fires each name on its own
    thread, waits for all of them to register in the same (parked) window,
    releases the window, and returns ``{name: result}``.
    """
    release = threading.Event()

    class _GatedTime:
        """Replaces batch_resolver's ``time`` so only *its* sleep is gated.

        Patching ``batch_resolver.time.sleep`` would mutate the shared global
        ``time`` module and freeze the test's own ``time.sleep`` too; swapping
        the module reference on ``batch_resolver`` keeps the effect local.
        """

        def sleep(self, _seconds):
            release.wait()

        def __getattr__(self, name):
            return getattr(time, name)

    monkeypatch.setattr(batch_resolver, "time", _GatedTime())
    # Non-zero so _run_window actually calls the (now gated) sleep.
    monkeypatch.setattr(timing, "IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS", 0.5)

    def run(resolver, names):
        results: dict[str, object] = {}
        errors: dict[str, BaseException] = {}

        def worker(name):
            try:
                results[name] = resolver.resolve(name)
            except Exception as exc:  # noqa: BLE001 - captured for assertions
                errors[name] = exc

        threads = [threading.Thread(target=worker, args=(n,)) for n in names]
        for t in threads:
            t.start()
        # The window thread is parked in the gated sleep, so nothing clears the
        # pending set: a brief wait guarantees every worker has registered.
        time.sleep(0.1)
        release.set()
        for t in threads:
            t.join()
        run.errors = errors
        return results

    run.errors = {}
    return run


def test_batch_uses_collection_for_multiple(gated_window):
    cards = [_card("Lightning Bolt", "u1"), _card("Island", "u2"), _card("Forest", "u3")]
    session = _RecordingSession(cards)

    def fetch_one(name, set_code):  # must NOT be used when batching
        raise AssertionError("fetch_one should not be called for a multi-card batch")

    resolver = ScryfallBatchResolver(session, fetch_one)
    results = gated_window(resolver, ["Lightning Bolt", "Island", "Forest"])

    assert results["Lightning Bolt"]["id"] == "u1"
    assert results["Island"]["id"] == "u2"
    assert results["Forest"]["id"] == "u3"
    # One POST carrying all three identifiers — not three separate calls.
    assert len(session.post_calls) == 1
    assert len(session.post_calls[0]) == 3


def test_single_card_uses_named_endpoint():
    """A window with exactly one card uses the per-card /cards/named path."""
    session = _RecordingSession([])
    called = []

    def fetch_one(name, set_code):
        called.append((name, set_code))
        return {"name": name, "id": "solo", "set": set_code, "collector_number": "7"}

    resolver = ScryfallBatchResolver(session, fetch_one)
    result = resolver.resolve("Black Lotus", set_code="lea")

    assert result["id"] == "solo"
    assert called == [("Black Lotus", "lea")]
    assert session.post_calls == []  # collection endpoint never touched


def test_batch_chunks_at_max_identifiers(gated_window):
    cards = [_card(f"Card {i}", f"u{i}") for i in range(80)]
    session = _RecordingSession(cards)
    resolver = ScryfallBatchResolver(session, lambda n, s: None, chunk_size=75)

    results = gated_window(resolver, [f"Card {i}" for i in range(80)])

    assert len(results) == 80
    assert all(results[f"Card {i}"]["id"] == f"u{i}" for i in range(80))
    # 80 identifiers → two chunks (75 + 5).
    assert [len(c) for c in session.post_calls] == [75, 5]


def test_face_name_resolves_to_combined_card(gated_window):
    split = _card("Wear // Tear", "usplit", faces=["Wear", "Tear"])
    other = _card("Lightning Bolt", "ubolt")
    session = _RecordingSession([split, other])
    resolver = ScryfallBatchResolver(session, lambda n, s: None)

    # Request the combined name alongside an unrelated card so it batches; the
    # combined-name request must resolve to the split card.
    results = gated_window(resolver, ["Wear // Tear", "Lightning Bolt"])

    assert results["Wear // Tear"]["id"] == "usplit"


def test_unmatched_identifier_returns_none(gated_window):
    session = _RecordingSession([_card("Real Card", "ureal")])
    resolver = ScryfallBatchResolver(session, lambda n, s: None)

    results = gated_window(resolver, ["Real Card", "Ghost Card"])

    assert results["Real Card"]["id"] == "ureal"
    assert results["Ghost Card"] is None  # not_found → None, not an error


def test_batch_http_error_propagates(gated_window):
    class _FailingSession:
        def post(self, url, json, timeout):
            raise RuntimeError("boom")

    resolver = ScryfallBatchResolver(_FailingSession(), lambda n, s: None)
    gated_window(resolver, ["A", "B"])

    # Every caller in the failed window sees the error and can retry.
    assert set(gated_window.errors) == {"A", "B"}


def test_duplicate_names_share_one_slot(gated_window):
    session = _RecordingSession([_card("Island", "uisland")])
    fetch_calls = []

    def fetch_one(name, set_code):
        fetch_calls.append(name)
        return {"name": name, "id": "uisland"}

    resolver = ScryfallBatchResolver(session, fetch_one)

    # Three concurrent requests for the same name coalesce onto one entry, so
    # the window holds a single unique identifier and uses /cards/named once.
    results = gated_window(resolver, ["Island", "Island", "Island"])

    assert results["Island"]["id"] == "uisland"
    assert fetch_calls == ["Island"]  # one lookup for three requests
    assert session.post_calls == []  # single unique id → named endpoint, not collection
