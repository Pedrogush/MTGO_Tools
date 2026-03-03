#!/usr/bin/env python3
"""Convert JSON cache files to msgpack sidecars for faster startup.

Run this once after your cache files have been downloaded or rebuilt to create
``.msgpack`` sidecars.  The app will then prefer the faster binary format on
subsequent startups.  The original ``.json`` files are preserved as a fallback.

Files converted
---------------
- ``data/atomic_cards_index.json``  → ``data/atomic_cards_index.msgpack``
- ``cache/card_images/bulk_data.json``  → ``cache/card_images/bulk_data.msgpack``
- ``cache/card_images/printings_v2.json``  → ``cache/card_images/printings_v2.msgpack``

Usage::

    python scripts/convert_to_msgpack.py
    python scripts/convert_to_msgpack.py --only atomic
    python scripts/convert_to_msgpack.py --only bulk
    python scripts/convert_to_msgpack.py --only printings
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from loguru import logger

from utils.atomic_io import atomic_write_msgpack
from utils.card_images import BULK_DATA_CACHE, PRINTING_INDEX_CACHE
from utils.constants import CARD_DATA_DIR

_ATOMIC_INDEX = CARD_DATA_DIR / "atomic_cards_index.json"

TARGETS: dict[str, Path] = {
    "atomic": _ATOMIC_INDEX,
    "bulk": BULK_DATA_CACHE,
    "printings": PRINTING_INDEX_CACHE,
}


def _convert_file(json_path: Path) -> bool:
    """Convert *json_path* to a ``.msgpack`` sidecar.

    Returns *True* on success, *False* when the source file is missing or the
    conversion fails.
    """
    if not json_path.exists():
        logger.warning("JSON file not found, skipping: {}", json_path)
        return False

    msg_path = json_path.with_suffix(".msgpack")
    size_mb = json_path.stat().st_size / (1024 * 1024)
    logger.info("Converting {} ({:.1f} MB) …", json_path.name, size_mb)

    t0 = time.perf_counter()
    try:
        data = json.loads(json_path.read_bytes())
    except Exception as exc:
        logger.error("Failed to read {}: {}", json_path.name, exc)
        return False
    load_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    try:
        atomic_write_msgpack(msg_path, data)
    except Exception as exc:
        logger.error("Failed to write {}: {}", msg_path.name, exc)
        return False
    write_ms = (time.perf_counter() - t1) * 1000

    msg_size_mb = msg_path.stat().st_size / (1024 * 1024)
    ratio = (1 - msg_path.stat().st_size / json_path.stat().st_size) * 100
    logger.info(
        "  {} → {}: {:.1f} MB ({:.0f}% smaller) | json_load={:.0f}ms msg_write={:.0f}ms",
        json_path.name,
        msg_path.name,
        msg_size_mb,
        ratio,
        load_ms,
        write_ms,
    )
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--only",
        choices=list(TARGETS.keys()),
        metavar="TARGET",
        help="Convert only the specified target (%(choices)s).",
    )
    args = parser.parse_args()

    targets = {args.only: TARGETS[args.only]} if args.only else TARGETS

    t_start = time.perf_counter()
    successes = sum(_convert_file(path) for path in targets.values())
    elapsed = time.perf_counter() - t_start

    logger.info(
        "Done: {}/{} files converted in {:.1f}s",
        successes,
        len(targets),
        elapsed,
    )
    return 0 if successes == len(targets) else 1


if __name__ == "__main__":
    sys.exit(main())
