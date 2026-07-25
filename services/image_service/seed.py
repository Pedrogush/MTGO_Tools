"""First-run seeding of the card-image bulk data from a bundled snapshot.

A fresh install otherwise has to download Scryfall's ~130 MB (gzipped) bulk
metadata before the local image index exists; until it lands, every card image
falls back to per-card API lookups. To make a cold start behave like a warm one,
the installer ships ``bulk_data.json.gz`` alongside the executable and this
module places it into the image cache on first launch — so the bulk file is
already present and image resolution is local from the very first deck view.

The cache stores the bulk file gzip-compressed (see
:mod:`services.image_service.bulk_store`), which is exactly the seed's format, so
seeding is a verbatim copy — no decompression — landing the compact ~130 MB form
directly.

Only the bulk file is seeded; the compact printing index
(``printings_v<N>.json``) is rebuilt from it locally on first launch (a few
seconds, no network), which keeps the build step to a single download.

The bundled snapshot ages like any other: the app's normal freshness check
re-downloads a fresher bulk file once the seed is old enough, so a stale seed is
self-correcting, never a permanent pin.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from loguru import logger

from services.image_service import schemas
from utils.constants.paths import resource_path

# Env override so a dev/test run can point at a seed directory explicitly.
SEED_DIR_ENV_VAR = "MTGO_TOOLS_SEED_DIR"

# Stream the copy in 1 MiB chunks rather than buffering the whole file.
_COPY_CHUNK_BYTES = 1024 * 1024


def _default_seed_source() -> Path | None:
    """Locate the bundled seed directory, or None when there is nothing to seed."""
    override = os.getenv(SEED_DIR_ENV_VAR)
    if override:
        return Path(override).expanduser()
    if getattr(sys, "frozen", False):
        # Installed build: the installer places seed files next to the exe.
        return Path(sys.executable).resolve().parent / "seed"
    # Dev/source runs normally already have a populated cache; a repo-local
    # ``seed/`` directory is honored if present but is not expected to exist.
    candidate = resource_path("seed")
    return candidate if candidate.is_dir() else None


def _seed_targets() -> list[tuple[str, Path]]:
    """(source filename, destination path) pairs — read live so tests can patch."""
    bulk = schemas.BULK_DATA_CACHE
    return [(f"{bulk.name}.gz", bulk)]


def _copy_atomic(gz_path: Path, target: Path) -> None:
    """Copy the gzip seed to *target* verbatim via a temp file + atomic rename.

    The cache stores the bulk file gzip-compressed, which is the seed's format,
    so this is a plain byte copy — no decompression.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(target.parent), suffix=".seedtmp")
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, open(gz_path, "rb") as src:
            shutil.copyfileobj(src, out, length=_COPY_CHUNK_BYTES)
        os.replace(tmp_path, target)
    except BaseException:
        tmp_path.unlink(missing_ok=True)
        raise


def seed_image_cache_if_needed(source_dir: Path | None = None) -> list[Path]:
    """Decompress any bundled seed files whose targets don't yet exist.

    Returns the list of destination paths written (empty when there's nothing to
    seed or everything is already present). Never raises: seeding is a
    best-effort head start, and the normal download path remains the fallback.
    """
    source = source_dir or _default_seed_source()
    if source is None or not source.is_dir():
        return []

    seeded: list[Path] = []
    for gz_name, target in _seed_targets():
        gz_path = source / gz_name
        if target.exists() or not gz_path.is_file():
            continue
        try:
            _copy_atomic(gz_path, target)
        except Exception as exc:
            logger.warning(f"Failed to seed {target.name} from {gz_path}: {exc}")
            continue
        seeded.append(target)
        logger.info(f"Seeded {target.name} from bundled card data ({gz_path.name})")
    return seeded


__all__ = ["seed_image_cache_if_needed", "SEED_DIR_ENV_VAR"]
