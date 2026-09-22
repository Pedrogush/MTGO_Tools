#!/usr/bin/env python3
"""Clear all caches except card images.

This is the dev-checkout twin of what the uninstaller does to
``%LOCALAPPDATA%/MTGO Tools/cache`` ([UninstallDelete] in
packaging/installer.iss): everything under ``cache/`` is regenerable, so the
whole directory goes. Anything a person authored therefore must not live here --
deck version history is kept in ``DECK_HISTORY_DIR`` beside ``config/`` for
exactly that reason.

``deck_vcs`` is preserved anyway. It is where history lived before the root
moved, and a developer checkout can still hold one; a cache clear is not the
place to find out that the move missed a copy.
"""

from __future__ import annotations

import shutil
from pathlib import Path

CACHE_DIR = Path("cache")
#: ``card_images`` is regenerable but expensive (thousands of downloads);
#: ``deck_vcs`` is a leftover history root that nothing can regenerate at all.
PRESERVE = {"card_images", "deck_vcs"}


def clear_caches(cache_dir: Path = CACHE_DIR) -> int:
    """Remove all cache files and directories except :data:`PRESERVE`; count removals."""
    if not cache_dir.exists():
        print("No cache directory found")
        return 0

    removed_count = 0
    preserved_count = 0

    for item in cache_dir.iterdir():
        if item.name in PRESERVE:
            preserved_count += 1
            print(f"Preserving: {item}")
            continue

        if item.is_file():
            item.unlink()
            print(f"Removed file: {item}")
            removed_count += 1
        elif item.is_dir():
            shutil.rmtree(item)
            print(f"Removed directory: {item}")
            removed_count += 1

    print(f"\nCleared {removed_count} items, preserved {preserved_count} items")
    return removed_count


if __name__ == "__main__":
    clear_caches()
