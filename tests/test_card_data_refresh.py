from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from repositories.card_repository import CardDataManager
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


def _card(name: str, mana_cost: str, text: str, color: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "manaCost": mana_cost,
        "manaValue": 1,
        "type": "Instant",
        "text": text,
        "colors": [color] if color else [],
        "colorIdentity": [color] if color else [],
        "legalities": {"modern": "Legal"},
    }


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

    index_path = tmp_path / "atomic_cards_index_v3.json"
    raw = json.loads(index_path.read_text(encoding="utf-8"))
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


def test_ensure_latest_skips_download_when_only_etag_changes(tmp_path: Path, monkeypatch):
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
