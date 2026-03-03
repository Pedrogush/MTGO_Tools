"""Tests for utils/data_cache_io.py."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from utils.data_cache_io import (
    AutoCacheLoader,
    DataCacheLoader,
    JsonCacheLoader,
    MsgpackCacheLoader,
    get_loader,
    load_cache,
    set_loader,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SAMPLE: dict[str, Any] = {
    "cards": [{"name": "Lightning Bolt", "mana_cost": "{R}"}],
    "cards_by_name": {"lightning bolt": {"name": "Lightning Bolt"}},
}


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_msgpack(path: Path, data: Any) -> None:
    import msgpack

    path.write_bytes(msgpack.packb(data, use_bin_type=True))


# ---------------------------------------------------------------------------
# JsonCacheLoader
# ---------------------------------------------------------------------------


def test_json_loader_loads_dict(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    _write_json(p, _SAMPLE)
    result = JsonCacheLoader().load(p)
    assert result["cards"][0]["name"] == "Lightning Bolt"


def test_json_loader_loads_list(tmp_path: Path) -> None:
    p = tmp_path / "list.json"
    _write_json(p, [1, 2, 3])
    assert JsonCacheLoader().load(p) == [1, 2, 3]


# ---------------------------------------------------------------------------
# MsgpackCacheLoader
# ---------------------------------------------------------------------------


def test_msgpack_loader_loads_dict(tmp_path: Path) -> None:
    p = tmp_path / "data.msgpack"
    _write_msgpack(p, _SAMPLE)
    result = MsgpackCacheLoader().load(p)
    assert result["cards"][0]["name"] == "Lightning Bolt"


def test_msgpack_loader_loads_list(tmp_path: Path) -> None:
    p = tmp_path / "list.msgpack"
    _write_msgpack(p, [10, 20, 30])
    assert MsgpackCacheLoader().load(p) == [10, 20, 30]


# ---------------------------------------------------------------------------
# AutoCacheLoader
# ---------------------------------------------------------------------------


def test_auto_loader_falls_back_to_json_when_no_msgpack(tmp_path: Path) -> None:
    p = tmp_path / "data.json"
    _write_json(p, _SAMPLE)
    result = AutoCacheLoader().load(p)
    assert result["cards"][0]["name"] == "Lightning Bolt"


def test_auto_loader_prefers_msgpack_when_sidecar_exists(tmp_path: Path) -> None:
    json_path = tmp_path / "data.json"
    msg_path = tmp_path / "data.msgpack"
    _write_json(json_path, {"source": "json"})
    _write_msgpack(msg_path, {"source": "msgpack"})

    result = AutoCacheLoader().load(json_path)
    assert result["source"] == "msgpack"


def test_auto_loader_falls_back_to_json_on_corrupt_msgpack(tmp_path: Path) -> None:
    json_path = tmp_path / "data.json"
    msg_path = tmp_path / "data.msgpack"
    _write_json(json_path, {"source": "json"})
    msg_path.write_bytes(b"not valid msgpack content!!!")

    result = AutoCacheLoader(warn_on_fallback=False).load(json_path)
    assert result["source"] == "json"


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


def test_loaders_satisfy_protocol() -> None:
    assert isinstance(JsonCacheLoader(), DataCacheLoader)
    assert isinstance(MsgpackCacheLoader(), DataCacheLoader)
    assert isinstance(AutoCacheLoader(), DataCacheLoader)


# ---------------------------------------------------------------------------
# Module-level set_loader / get_loader / load_cache
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _restore_default_loader():
    """Restore the module-level loader after each test."""
    original = get_loader()
    yield
    set_loader(original)


def test_get_loader_returns_auto_by_default() -> None:
    assert isinstance(get_loader(), AutoCacheLoader)


def test_set_loader_replaces_default(tmp_path: Path) -> None:
    json_path = tmp_path / "data.json"
    msg_path = tmp_path / "data.msgpack"
    _write_json(json_path, {"source": "json"})
    _write_msgpack(msg_path, {"source": "msgpack"})

    # Force JSON loader — should ignore the sidecar
    set_loader(JsonCacheLoader())
    result = load_cache(json_path)
    assert result["source"] == "json"


def test_load_cache_uses_current_loader_msgpack(tmp_path: Path) -> None:
    json_path = tmp_path / "data.json"
    msg_path = tmp_path / "data.msgpack"
    _write_json(json_path, {"source": "json"})
    _write_msgpack(msg_path, {"source": "msgpack"})

    # Default AutoCacheLoader should prefer msgpack
    result = load_cache(json_path)
    assert result["source"] == "msgpack"


def test_set_loader_accepts_custom_implementation(tmp_path: Path) -> None:
    class AlwaysEmpty:
        def load(self, path: Path) -> Any:
            return {}

    set_loader(AlwaysEmpty())
    json_path = tmp_path / "data.json"
    _write_json(json_path, {"key": "value"})
    assert load_cache(json_path) == {}
