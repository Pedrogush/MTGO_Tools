"""Swappable cache loader interface for JSON and msgpack data files.

Provides a protocol-based loader interface and an ``AutoCacheLoader`` that
prefers msgpack (``.msgpack``) sidecars when available, falling back to the
original ``.json`` source transparently.

Usage::

    from pathlib import Path
    from utils.data_cache_io import load_cache, set_loader, JsonCacheLoader

    # Default: AutoCacheLoader (msgpack if available, else JSON)
    data = load_cache(Path("data/atomic_cards_index.json"))

    # Force JSON only (e.g. for debugging):
    set_loader(JsonCacheLoader())

    # Restore default auto behaviour:
    set_loader(AutoCacheLoader())
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class DataCacheLoader(Protocol):
    """Protocol for interchangeable data cache loaders."""

    def load(self, path: Path) -> Any:
        """Load and return deserialised data from *path*."""
        ...


class JsonCacheLoader:
    """Loads data from ``.json`` files."""

    def load(self, path: Path) -> Any:
        return json.loads(path.read_bytes())


class MsgpackCacheLoader:
    """Loads data from ``.msgpack`` files."""

    def load(self, path: Path) -> Any:
        import msgpack  # lazy import – optional in environments without msgpack

        return msgpack.unpackb(path.read_bytes(), raw=False, strict_map_key=False)


class AutoCacheLoader:
    """Prefers a ``.msgpack`` sidecar when one exists; falls back to ``.json``.

    The sidecar path is derived by replacing the source file's suffix with
    ``.msgpack``.  For example, ``data/atomic_cards_index.json`` is tried as
    ``data/atomic_cards_index.msgpack`` first.

    Args:
        warn_on_fallback: If *True*, log a warning whenever the msgpack load
            fails and the loader falls back to JSON.
    """

    def __init__(self, *, warn_on_fallback: bool = True) -> None:
        self._warn_on_fallback = warn_on_fallback

    def load(self, path: Path) -> Any:
        msg_path = path.with_suffix(".msgpack")
        if msg_path.exists():
            try:
                return MsgpackCacheLoader().load(msg_path)
            except Exception as exc:
                if self._warn_on_fallback:
                    from loguru import logger

                    logger.warning(
                        "msgpack load failed for %s, falling back to JSON: %s",
                        msg_path,
                        exc,
                    )
        return JsonCacheLoader().load(path)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_default_loader: DataCacheLoader = AutoCacheLoader()


def get_loader() -> DataCacheLoader:
    """Return the current module-level cache loader."""
    return _default_loader


def set_loader(loader: DataCacheLoader) -> None:
    """Replace the module-level cache loader.

    Use this to force a specific format (e.g. ``JsonCacheLoader()`` for
    debugging) or to restore the default ``AutoCacheLoader()``.
    """
    global _default_loader
    _default_loader = loader


def load_cache(path: Path) -> Any:
    """Load data from *path* using the current default loader.

    The default loader is ``AutoCacheLoader``, which transparently uses a
    ``.msgpack`` sidecar when one is present alongside the JSON source.
    """
    return _default_loader.load(path)


__all__ = [
    "DataCacheLoader",
    "JsonCacheLoader",
    "MsgpackCacheLoader",
    "AutoCacheLoader",
    "get_loader",
    "set_loader",
    "load_cache",
]
