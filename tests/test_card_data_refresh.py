from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import msgspec.msgpack
import pytest

from repositories.card_repository import CardDataManager, load_card_manager
from repositories.card_repository import remote as card_data_remote


class _StubResponse:
    def __init__(self, *, headers: dict[str, str] | None = None, content: bytes = b""):
        self.headers = headers or {}
        self.content = content

    def raise_for_status(self) -> None:  # pragma: no cover - stub never errors
        return


def _build_bulk_zip(cards: dict[str, list[dict[str, Any]]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("AtomicCards.json", json.dumps({"data": cards}))
    return buffer.getvalue()


def _card(
    name: str,
    mana_cost: str,
    text: str,
    color: str | None = None,
    type_line: str = "Instant",
    legalities: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "manaCost": mana_cost,
        "manaValue": 1,
        "type": type_line,
        "text": text,
        "colors": [color] if color else [],
        "colorIdentity": [color] if color else [],
        "legalities": {"modern": "Legal"} if legalities is None else legalities,
    }


def _stale_head_stamp(tmp_path: Path) -> None:
    """Backdate the cached HEAD timestamp so the TTL fast-path is bypassed."""
    meta_path = tmp_path / "atomic_cards_meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta["head_checked_at"] = 0
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def _patch_requests(monkeypatch: pytest.MonkeyPatch, headers: dict[str, str], content: bytes):
    def fake_head(*_: Any, **__: Any) -> _StubResponse:
        return _StubResponse(headers=headers)

    def fake_get(*_: Any, **__: Any) -> _StubResponse:
        return _StubResponse(headers=headers, content=content)

    monkeypatch.setattr(card_data_remote.requests, "head", fake_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", fake_get, raising=False)


def test_ensure_latest_downloads_when_cache_missing(tmp_path: Path, monkeypatch):
    cards = {"Opt": [_card("Opt", "{U}", "Scry 1, draw a card.", "U")]}
    headers = {
        "etag": "v1",
        "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "content-length": "123",
    }
    content = _build_bulk_zip(cards)
    _patch_requests(monkeypatch, headers, content)

    manager = CardDataManager(tmp_path)
    manager.ensure_latest()

    meta = json.loads((tmp_path / "atomic_cards_meta.json").read_text(encoding="utf-8"))
    assert meta["etag"] == "v1"
    assert "sha512" in meta
    assert manager.get_card("Opt") is not None


def test_ensure_latest_strips_quotes_from_etag(tmp_path: Path, monkeypatch):
    """Quoted ETags (the HTTP-standard form) are normalized before storage.

    HTTP servers wrap ETag values in double quotes (e.g. ``ETag: "abc"``).
    The cache stores the bare token so later HEAD comparisons match.
    """
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    headers = {
        "etag": '"v1"',
        "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "content-length": "123",
    }
    _patch_requests(monkeypatch, headers, _build_bulk_zip(cards))

    CardDataManager(tmp_path).ensure_latest()

    meta = json.loads((tmp_path / "atomic_cards_meta.json").read_text(encoding="utf-8"))
    assert meta["etag"] == "v1"


def test_ensure_latest_skips_download_when_meta_matches(tmp_path: Path, monkeypatch):
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    headers = {
        "etag": "v1",
        "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "content-length": "123",
    }
    content = _build_bulk_zip(cards)
    _patch_requests(monkeypatch, headers, content)

    first_manager = CardDataManager(tmp_path)
    first_manager.ensure_latest()
    _stale_head_stamp(tmp_path)

    download_called = False

    def fake_get(*_: Any, **__: Any) -> _StubResponse:
        nonlocal download_called
        download_called = True
        return _StubResponse(headers=headers, content=content)

    def fake_head(*_: Any, **__: Any) -> _StubResponse:
        return _StubResponse(headers=headers)

    monkeypatch.setattr(card_data_remote.requests, "head", fake_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", fake_get, raising=False)

    second_manager = CardDataManager(tmp_path)
    second_manager.ensure_latest()

    assert download_called is False
    assert second_manager.get_card("Opt") is not None
    # The matching HEAD re-stamps the TTL (_touch_head_checked) so the next
    # readiness check can take the warm-cache fast path.
    meta = json.loads((tmp_path / "atomic_cards_meta.json").read_text(encoding="utf-8"))
    assert meta["head_checked_at"] > 0


def test_ensure_latest_downloads_when_meta_differs(tmp_path: Path, monkeypatch):
    initial_cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    initial_headers = {
        "etag": "v1",
        "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "content-length": "123",
    }
    initial_content = _build_bulk_zip(initial_cards)
    _patch_requests(monkeypatch, initial_headers, initial_content)

    manager = CardDataManager(tmp_path)
    manager.ensure_latest()
    _stale_head_stamp(tmp_path)

    new_cards = {"Lightning Bolt": [_card("Lightning Bolt", "{R}", "3 damage", "R")]}
    new_headers = {
        "etag": "v2",
        "last-modified": "Tue, 02 Jan 2024 00:00:00 GMT",
        "content-length": "456",
    }
    new_content = _build_bulk_zip(new_cards)

    download_called = False

    def fake_get(*_: Any, **__: Any) -> _StubResponse:
        nonlocal download_called
        download_called = True
        return _StubResponse(headers=new_headers, content=new_content)

    def fake_head(*_: Any, **__: Any) -> _StubResponse:
        return _StubResponse(headers=new_headers)

    monkeypatch.setattr(card_data_remote.requests, "head", fake_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", fake_get, raising=False)

    manager = CardDataManager(tmp_path)
    manager.ensure_latest()

    meta = json.loads((tmp_path / "atomic_cards_meta.json").read_text(encoding="utf-8"))
    assert download_called is True
    assert meta["etag"] == "v2"
    assert manager.get_card("Lightning Bolt") is not None


def test_index_persists_name_map_as_indices(tmp_path: Path, monkeypatch):
    cards = {"Opt": [_card("Opt", "{U}", "Scry 1, draw a card.", "U")]}
    headers = {"etag": "v1", "last-modified": "x", "content-length": "1"}
    _patch_requests(monkeypatch, headers, _build_bulk_zip(cards))

    CardDataManager(tmp_path).ensure_latest()

    index_path = tmp_path / "atomic_cards_index_v3.msgpack"
    raw = msgspec.msgpack.decode(index_path.read_bytes())
    # cards_by_name is persisted as alias -> int index, not duplicated objects.
    assert all(isinstance(v, int) for v in raw["cards_by_name"].values())
    assert raw["cards"][raw["cards_by_name"]["opt"]]["name"] == "Opt"


def test_reloaded_get_card_shares_card_objects(tmp_path: Path, monkeypatch):
    cards = {"Opt": [_card("Opt", "{U}", "Scry 1, draw a card.", "U")]}
    headers = {"etag": "v1", "last-modified": "x", "content-length": "1"}
    _patch_requests(monkeypatch, headers, _build_bulk_zip(cards))

    CardDataManager(tmp_path).ensure_latest()

    # Fresh manager loads from disk and resolves the index map back to the same
    # CardEntry instance held in the cards list (no duplicated objects).
    reloaded = CardDataManager(tmp_path)
    reloaded.ensure_latest()
    card = reloaded.get_card("Opt")
    assert card is not None
    assert any(card is entry for entry in reloaded._cards or [])


def test_ensure_latest_etag_change_alone_does_not_force_refresh(tmp_path: Path, monkeypatch):
    """An ETag change with an unchanged size does not trigger a re-download.

    ``ensure_latest`` never compares ETags: the refresh decision is driven
    purely by ``content-length`` (see card_data_manager.py:71). Here the ETag
    flips from ``v1`` to ``v2`` while the size stays ``123``, so no GET is made.
    """
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    initial_headers = {
        "etag": "v1",
        "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
        "content-length": "123",
    }
    content = _build_bulk_zip(cards)
    _patch_requests(monkeypatch, initial_headers, content)

    first_manager = CardDataManager(tmp_path)
    first_manager.ensure_latest()
    _stale_head_stamp(tmp_path)

    new_headers = {
        "etag": "v2",
        "last-modified": "Tue, 02 Jan 2024 00:00:00 GMT",
        "content-length": "123",
    }

    download_called = False

    def fake_get(*_: Any, **__: Any) -> _StubResponse:
        nonlocal download_called
        download_called = True
        return _StubResponse(headers=new_headers, content=content)

    def fake_head(*_: Any, **__: Any) -> _StubResponse:
        return _StubResponse(headers=new_headers)

    monkeypatch.setattr(card_data_remote.requests, "head", fake_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", fake_get, raising=False)

    second_manager = CardDataManager(tmp_path)
    second_manager.ensure_latest()

    assert download_called is False
    assert second_manager.get_card("Opt") is not None


def test_ensure_latest_skips_head_on_fresh_warm_cache(tmp_path: Path, monkeypatch):
    """A recent, present index loads without touching the network (QW3)."""
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    headers = {"etag": "v1", "content-length": "123"}
    content = _build_bulk_zip(cards)
    _patch_requests(monkeypatch, headers, content)

    first_manager = CardDataManager(tmp_path)
    first_manager.ensure_latest()

    head_called = False

    def fake_head(*_: Any, **__: Any) -> _StubResponse:
        nonlocal head_called
        head_called = True
        return _StubResponse(headers=headers)

    monkeypatch.setattr(card_data_remote.requests, "head", fake_head, raising=False)

    second_manager = CardDataManager(tmp_path)
    second_manager.ensure_latest()

    assert head_called is False
    assert second_manager.get_card("Opt") is not None


def test_ensure_latest_uses_cache_when_offline(tmp_path: Path, monkeypatch):
    """Offline launch with a present (stale-TTL) index still loads from cache."""
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    headers = {"etag": "v1", "content-length": "123"}
    content = _build_bulk_zip(cards)
    _patch_requests(monkeypatch, headers, content)

    first_manager = CardDataManager(tmp_path)
    first_manager.ensure_latest()
    _stale_head_stamp(tmp_path)

    def offline_head(*_: Any, **__: Any) -> _StubResponse:
        raise RuntimeError("network unreachable")

    download_called = False

    def fake_get(*_: Any, **__: Any) -> _StubResponse:
        nonlocal download_called
        download_called = True
        return _StubResponse(headers=headers, content=content)

    # HEAD fails, so fetch_dataset_headers returns None and the GET branch is
    # never reached; the download-fails fallback is covered separately by
    # test_ensure_latest_falls_back_to_cache_when_download_fails.
    monkeypatch.setattr(card_data_remote.requests, "head", offline_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", fake_get, raising=False)

    second_manager = CardDataManager(tmp_path)
    second_manager.ensure_latest()

    # The card is served strictly from the on-disk cache: no GET was issued.
    assert download_called is False
    assert second_manager.get_card("Opt") is not None


def test_ensure_latest_falls_back_to_cache_when_download_fails(tmp_path: Path, monkeypatch):
    """A forced refresh whose GET fails keeps serving the existing cache.

    This exercises the download-failed-with-existing-cache branch
    (card_data_manager.py: ``logger.warning(..., using cache)``): unlike the
    offline test, the HEAD succeeds so ``needs_refresh`` is True and the GET
    branch is actually reached and raises.
    """
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    headers = {"etag": "v1", "content-length": "123"}
    content = _build_bulk_zip(cards)
    _patch_requests(monkeypatch, headers, content)

    first_manager = CardDataManager(tmp_path)
    first_manager.ensure_latest()
    _stale_head_stamp(tmp_path)

    def failing_get(*_: Any, **__: Any) -> _StubResponse:
        raise RuntimeError("download interrupted")

    monkeypatch.setattr(card_data_remote.requests, "get", failing_get, raising=False)

    second_manager = CardDataManager(tmp_path)
    # force=True so we skip the size comparison and go straight to the GET,
    # guaranteeing the failure path is the download branch and not a no-op.
    second_manager.ensure_latest(force=True)

    assert second_manager.get_card("Opt") is not None


def test_ensure_latest_raises_when_download_fails_and_no_cache(tmp_path: Path, monkeypatch):
    """Cold start with no cache and a failing GET surfaces a clear RuntimeError."""

    def failing_get(*_: Any, **__: Any) -> _StubResponse:
        raise RuntimeError("network unreachable")

    def fake_head(*_: Any, **__: Any) -> _StubResponse:
        return _StubResponse(headers={"etag": "v1", "content-length": "123"})

    monkeypatch.setattr(card_data_remote.requests, "head", fake_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", failing_get, raising=False)

    manager = CardDataManager(tmp_path)
    with pytest.raises(RuntimeError, match="no cache is available"):
        manager.ensure_latest()


def test_ensure_latest_force_redownloads_warm_cache(tmp_path: Path, monkeypatch):
    """``force=True`` bypasses the warm-cache fast path and re-downloads."""
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    headers = {"etag": "v1", "content-length": "123"}
    content = _build_bulk_zip(cards)
    _patch_requests(monkeypatch, headers, content)

    first_manager = CardDataManager(tmp_path)
    first_manager.ensure_latest()

    new_cards = {"Lightning Bolt": [_card("Lightning Bolt", "{R}", "3 damage", "R")]}
    new_headers = {"etag": "v2", "content-length": "456"}
    new_content = _build_bulk_zip(new_cards)

    download_called = False

    def fake_get(*_: Any, **__: Any) -> _StubResponse:
        nonlocal download_called
        download_called = True
        return _StubResponse(headers=new_headers, content=new_content)

    def fake_head(*_: Any, **__: Any) -> _StubResponse:
        return _StubResponse(headers=new_headers)

    monkeypatch.setattr(card_data_remote.requests, "head", fake_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", fake_get, raising=False)

    # The cache is fresh, so without force this would skip the network entirely.
    second_manager = CardDataManager(tmp_path)
    second_manager.ensure_latest(force=True)

    assert download_called is True
    assert second_manager.get_card("Lightning Bolt") is not None


def test_load_card_manager_force_downloads(tmp_path: Path, monkeypatch):
    """The module-level helper builds a manager and honours ``force``."""
    cards = {"Opt": [_card("Opt", "{U}", "", "U")]}
    headers = {"etag": "v1", "content-length": "123"}
    _patch_requests(monkeypatch, headers, _build_bulk_zip(cards))

    manager = load_card_manager(tmp_path, force=True)

    assert isinstance(manager, CardDataManager)
    assert manager.is_loaded is True
    assert manager.get_card("Opt") is not None


def test_loaded_manager_query_api(tmp_path: Path, monkeypatch):
    """A loaded manager answers search_cards/available_formats consistently."""
    cards = {
        "Opt": [
            _card(
                "Opt",
                "{U}",
                "Scry 1, draw a card.",
                "U",
                type_line="Instant",
                legalities={"modern": "Legal", "legacy": "Legal"},
            )
        ],
        "Lightning Bolt": [
            _card(
                "Lightning Bolt",
                "{R}",
                "Deal 3 damage.",
                "R",
                type_line="Instant",
                legalities={"legacy": "Legal"},
            )
        ],
        "Llanowar Elves": [
            _card(
                "Llanowar Elves",
                "{G}",
                "{T}: Add {G}.",
                "G",
                type_line="Creature — Elf Druid",
                legalities={"modern": "Legal"},
            )
        ],
    }
    headers = {"etag": "v1", "content-length": "123"}
    _patch_requests(monkeypatch, headers, _build_bulk_zip(cards))

    manager = CardDataManager(tmp_path)
    manager.ensure_latest()

    by_name = manager.search_cards(query="opt")
    assert [c.name for c in by_name] == ["Opt"]

    by_color = manager.search_cards(color_identity=["R"])
    assert [c.name for c in by_color] == ["Lightning Bolt"]

    # format_filter keeps only cards Legal in that format (Lightning Bolt is
    # legacy-only, so it is excluded from a modern query).
    by_format = manager.search_cards(format_filter="modern")
    assert sorted(c.name for c in by_format) == ["Llanowar Elves", "Opt"]

    # type_filter is a substring match against the (lowercased) type line.
    by_type = manager.search_cards(type_filter="creature")
    assert [c.name for c in by_type] == ["Llanowar Elves"]

    limited = manager.search_cards(limit=1)
    assert len(limited) == 1

    # available_formats returns the de-duplicated, sorted set of formats in
    # which at least one card is Legal (see each card's ``legalities`` above).
    assert manager.available_formats() == ["legacy", "modern"]


def test_query_api_requires_loaded_data(tmp_path: Path):
    """The query API refuses to run before ensure_latest has loaded data."""
    manager = CardDataManager(tmp_path)
    assert manager.is_loaded is False
    with pytest.raises(RuntimeError, match="not loaded"):
        manager.get_card("Opt")
    with pytest.raises(RuntimeError, match="not loaded"):
        manager.search_cards(query="opt")
    with pytest.raises(RuntimeError, match="not loaded"):
        manager.available_formats()
