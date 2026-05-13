"""On-disk format for the atomic-cards index and its metadata sidecar.

Owns path resolution, the module-level msgspec decoder (reused across loads),
atomic JSON writes, and the meta-JSON read helper.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import msgspec
import msgspec.json
from loguru import logger

from services.card_data_service.schemas import CardIndex
from utils.atomic_io import atomic_write_json
from utils.constants import CARD_DATA_DIR

# Reusing the decoder avoids re-building it on every call, which matters for
# repeat loads (e.g. force-refresh).
_card_index_decoder: msgspec.json.Decoder[CardIndex] = msgspec.json.Decoder(CardIndex)


def resolve_paths(data_dir: Path | str = CARD_DATA_DIR) -> tuple[Path, Path, Path]:
    """Return ``(data_dir, index_path, meta_path)`` after ensuring ``data_dir`` exists.

    The ``_v2`` filename invalidates pre-double-faced-aware caches.
    """
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base, base / "atomic_cards_index_v2.json", base / "atomic_cards_meta.json"


def load_index(index_path: Path) -> CardIndex:
    if not index_path.exists():
        raise RuntimeError("Card data index missing or invalid")
    try:
        data = index_path.read_bytes()
        return _card_index_decoder.decode(data)
    except (msgspec.DecodeError, OSError) as exc:
        raise RuntimeError(f"Card data index missing or invalid: {exc}") from exc


def write_index(index_path: Path, index: dict[str, Any]) -> None:
    atomic_write_json(index_path, index, ensure_ascii=False)


def load_meta(meta_path: Path) -> dict[str, Any] | None:
    if not meta_path.exists():
        return None
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning(f"Invalid JSON at {meta_path}: {exc}")
        return None


def write_meta(meta_path: Path, meta: dict[str, Any]) -> None:
    atomic_write_json(meta_path, meta, ensure_ascii=False)


__all__ = [
    "load_index",
    "load_meta",
    "resolve_paths",
    "write_index",
    "write_meta",
]
