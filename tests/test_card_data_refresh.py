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

    def offline_get(*_: Any, **__: Any) -> _StubResponse:
        raise RuntimeError("network unreachable")

    monkeypatch.setattr(card_data_remote.requests, "head", offline_head, raising=False)
    monkeypatch.setattr(card_data_remote.requests, "get", offline_get, raising=False)

    second_manager = CardDataManager(tmp_path)
    second_manager.ensure_latest()

    assert second_manager.get_card("Opt") is not None
