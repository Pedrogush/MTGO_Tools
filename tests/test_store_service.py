"""Tests for StoreService JSON persistence helper."""

import json
from pathlib import Path

import pytest

import services.store_service as store_service_module
from services.store_service import StoreService, get_store_service


@pytest.fixture(autouse=True)
def reset_store_service():
    """Ensure global store service state is reset between tests."""
    store_service_module._default_store_service = None  # type: ignore[attr-defined]
    yield
    store_service_module._default_store_service = None  # type: ignore[attr-defined]


@pytest.fixture
def store_service() -> StoreService:
    """Provide a fresh StoreService instance."""
    return StoreService()


def test_load_store_missing_file_returns_empty_dict(tmp_path: Path, store_service: StoreService):
    """Loading a non-existent store returns an empty dictionary."""
    path = tmp_path / "missing.json"

    result = store_service.load_store(path)

    assert result == {}


def test_load_store_reads_valid_json(tmp_path: Path, store_service: StoreService):
    """Valid JSON payload is loaded into a dictionary."""
    path = tmp_path / "store.json"
    payload = {"notes": {"deck": "Bring 3 Disdainful Stroke"}, "version": 1}
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = store_service.load_store(path)

    assert result == payload


def test_load_store_returns_empty_on_invalid_json(tmp_path: Path, store_service: StoreService):
    """Invalid JSON is ignored and returns an empty dict."""
    path = tmp_path / "corrupt.json"
    path.write_text("{bad json", encoding="utf-8")

    result = store_service.load_store(path)

    assert result == {}


def test_load_store_handles_oserror(monkeypatch, tmp_path: Path, store_service: StoreService):
    """OS errors while reading a store fallback to an empty dict."""
    path = tmp_path / "store.json"
    path.write_text("{}", encoding="utf-8")

    def fake_read_text(self, *args, **kwargs):  # pylint: disable=unused-argument
        raise OSError("boom")

    monkeypatch.setattr(type(path), "read_text", fake_read_text)

    result = store_service.load_store(path)

    assert result == {}


def test_save_store_writes_json_payload(tmp_path: Path, store_service: StoreService):
    """save_store creates parent directories and writes JSON data."""
    target = tmp_path / "nested" / "store.json"
    data = {"guides": {"matchup": ["Out 2 Bolt", "In 2 Aether Gust"]}}

    store_service.save_store(target, data)

    assert target.exists()
    contents = json.loads(target.read_text(encoding="utf-8"))
    assert contents == data


def test_save_store_preserves_unicode(tmp_path: Path, store_service: StoreService):
    """Unicode values should remain unescaped in the written file."""
    target = tmp_path / "notes.json"
    data = {"notes": "Bring S\u00e9ance for mirror"}  # Contains é

    store_service.save_store(target, data)

    raw = target.read_text(encoding="utf-8")
    assert "S\u00e9ance" in raw  # actual é character present
    assert "\\u00e9" not in raw  # ensure it was not escaped


def test_save_store_handles_write_errors(monkeypatch, tmp_path: Path, store_service: StoreService):
    """Errors during write operations are swallowed gracefully."""
    target = tmp_path / "store.json"

    def fake_atomic_write(*args, **kwargs):  # pylint: disable=unused-argument
        raise OSError("no space left on device")

    monkeypatch.setattr("services.store_service.atomic_write_json", fake_atomic_write)

    store_service.save_store(target, {"notes": {}})
    assert not target.exists()


def test_get_store_service_returns_singleton():
    """get_store_service should return the same instance across calls."""
    service_one = get_store_service()
    service_two = get_store_service()

    assert isinstance(service_one, StoreService)
    assert service_one is service_two
