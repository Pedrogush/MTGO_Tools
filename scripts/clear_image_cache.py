#!/usr/bin/env python3
"""Clear the card image cache for a reproducible cold-start state.

Removes the downloaded image files and the SQLite metadata database under
``cache/card_images`` so prefetch/warmup behavior can be measured from the
same empty state on every run. The Scryfall bulk data and the printings
index are *kept* by default — they are inputs to image resolution, not
images, and re-downloading them would dominate any perf iteration. Pass
``--all`` to wipe those too.

Usage (from the repo root):
    ./.venv/Scripts/python.exe scripts/clear_image_cache.py [--all] [--dry-run]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.image_service.schemas import (  # noqa: E402
    BULK_DATA_CACHE,
    IMAGE_CACHE_DIR,
    IMAGE_DB_PATH,
    IMAGE_SIZES,
    PRINTING_INDEX_CACHE,
)


def clear_image_cache(*, include_bulk_data: bool = False, dry_run: bool = False) -> None:
    if not IMAGE_CACHE_DIR.exists():
        print(f"No image cache directory at {IMAGE_CACHE_DIR}")
        return

    targets: list[Path] = [IMAGE_DB_PATH]
    targets += [IMAGE_CACHE_DIR / size for size in IMAGE_SIZES.values()]
    if include_bulk_data:
        targets += [BULK_DATA_CACHE, PRINTING_INDEX_CACHE]

    removed_files = 0
    for target in targets:
        if not target.exists():
            continue
        if target.is_dir():
            count = sum(1 for entry in target.rglob("*") if entry.is_file())
            print(f"{'Would remove' if dry_run else 'Removing'} {target} ({count} files)")
            if not dry_run:
                shutil.rmtree(target)
            removed_files += count
        else:
            print(f"{'Would remove' if dry_run else 'Removing'} {target}")
            if not dry_run:
                target.unlink()
            removed_files += 1

    kept = "" if include_bulk_data else " (bulk data + printings index kept; --all wipes them)"
    print(f"{'Would clear' if dry_run else 'Cleared'} {removed_files} files{kept}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--all",
        action="store_true",
        help="also remove the Scryfall bulk data and printings index",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would be removed without removing"
    )
    args = parser.parse_args()
    clear_image_cache(include_bulk_data=args.all, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
