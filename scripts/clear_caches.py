#!/usr/bin/env python3
"""Clear all caches except card images.

This is the dev-checkout twin of what the uninstaller does to
``%LOCALAPPDATA%/MTGO Tools/cache`` ([UninstallDelete] in
packaging/installer.iss): everything under ``cache/`` is regenerable, so the
whole directory goes. Anything a person authored therefore must not live here --
deck version history is kept in ``DECK_HISTORY_DIR`` and the saved-deck records
in ``DECK_RECORDS_DIR``, both beside ``config/``, for exactly that reason.

Their old locations are preserved anyway. A developer checkout can still hold a
``deck_vcs`` directory or a ``saved_decks.db`` from before they moved, and the
records file moves itself only when the app next opens it; a cache clear is not
the place to find out that the move has not happened yet.
"""

from __future__ import annotations

import shutil
from pathlib import Path

CACHE_DIR = Path("cache")
#: ``card_images`` is regenerable but expensive (thousands of downloads). The
#: other two are leftovers of the user's own work that nothing can regenerate at
#: all: a history root, and a records database still waiting to be migrated.
#: SQLite's sidecars are named too. They are normally transient, but a writer
#: that died mid-transaction leaves a *hot* journal, and a database kept without
#: the journal that rolls it back is a database kept corrupt.
PRESERVE = {
    "card_images",
    "deck_vcs",
    "saved_decks.db",
    "saved_decks.db-journal",
    "saved_decks.db-wal",
    "saved_decks.db-shm",
}


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
