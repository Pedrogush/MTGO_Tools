"""On-disk format for the atomic-cards index and its metadata sidecar.

Owns path resolution, the module-level msgspec decoder (reused across loads),
atomic index writes, and the meta-JSON read helper.

The index is persisted as ``msgspec.msgpack`` (binary): it decodes
substantially faster and is smaller on disk than the equivalent JSON, which
matters because the index is ~34k card records read on every startup. A
one-time migration converts a pre-existing JSON index to msgpack in place
(see :func:`migrate_legacy_index`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import msgspec
import msgspec.json
import msgspec.msgpack
from loguru import logger

from repositories.card_repository.schemas import CardIndex
from utils.atomic_io import atomic_write_bytes, atomic_write_json
from utils.constants import CARD_DATA_DIR
from utils.perf import timed

# Reusing the codecs avoids re-building them on every call, which matters for
# repeat loads (e.g. force-refresh).
_card_index_decoder: msgspec.msgpack.Decoder[CardIndex] = msgspec.msgpack.Decoder(CardIndex)
_card_index_encoder: msgspec.msgpack.Encoder = msgspec.msgpack.Encoder()


def resolve_paths(data_dir: Path | str = CARD_DATA_DIR) -> tuple[Path, Path, Path]:
    """Return ``(data_dir, index_path, meta_path)`` after ensuring ``data_dir`` exists.

    The ``_v2`` filename invalidates pre-double-faced-aware caches; the
    ``.msgpack`` extension distinguishes the binary index from the legacy JSON.
    """
    base = Path(data_dir)
    base.mkdir(parents=True, exist_ok=True)
    return base, base / "atomic_cards_index_v2.msgpack", base / "atomic_cards_meta.json"


def legacy_index_path(data_dir: Path | str = CARD_DATA_DIR) -> Path:
    """Return the path of the pre-msgpack JSON index (used for migration)."""
    return Path(data_dir) / "atomic_cards_index_v2.json"


def migrate_legacy_index(index_path: Path, legacy_path: Path) -> bool:
    """Convert a legacy JSON index to msgpack in place, if applicable.

    Returns ``True`` when a migration was performed. The legacy JSON file is
    removed afterwards so the conversion runs at most once. A corrupt legacy
    file is left untouched so the normal download/rebuild path can replace it.
    """
    if index_path.exists() or not legacy_path.exists():
        return False
    try:
        index = msgspec.json.decode(legacy_path.read_bytes(), type=CardIndex)
    except (msgspec.DecodeError, OSError) as exc:
        logger.warning(f"Could not migrate legacy card index {legacy_path}: {exc}")
        return False
    atomic_write_bytes(index_path, _card_index_encoder.encode(index))
    logger.info("Migrated card index from JSON to msgpack")
    try:
        legacy_path.unlink()
    except OSError:
        pass
    return True


@timed
def load_index(index_path: Path) -> CardIndex:
    if not index_path.exists():
        raise RuntimeError("Card data index missing or invalid")
    try:
        data = index_path.read_bytes()
        return _card_index_decoder.decode(data)
    except (msgspec.DecodeError, OSError) as exc:
        raise RuntimeError(f"Card data index missing or invalid: {exc}") from exc


def write_index(index_path: Path, index: dict[str, Any]) -> None:
    atomic_write_bytes(index_path, _card_index_encoder.encode(index))


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
    "legacy_index_path",
    "load_index",
    "load_meta",
    "migrate_legacy_index",
    "resolve_paths",
    "write_index",
    "write_meta",
]
