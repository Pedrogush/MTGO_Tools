#!/usr/bin/env python3
"""Clear all caches except card images.

This is the dev-checkout twin of what the uninstaller does to
``%LOCALAPPDATA%/MTGO Tools/cache`` ([UninstallDelete] in
packaging/installer.iss): everything under ``cache/`` is regenerable, so the
whole directory goes. Anything a person authored therefore must not live here --
deck version history is kept in ``DECK_HISTORY_DIR``, and the saved-deck records
together with the notes, outboard lists and sideboard guides the user typed in
``DECK_RECORDS_DIR``, both beside ``config/``, for exactly that reason.

Their old locations are preserved anyway. A developer checkout can still hold a
``deck_vcs`` directory, a ``saved_decks.db`` or the three metadata JSON files
from before they moved, and each of those moves itself only when the app next
opens it; a cache clear is not the place to find out that the move has not
happened yet.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

# Run as ``python scripts/clear_caches.py``, the interpreter puts ``scripts/``
# on the path rather than the checkout, so the import below is handed the root.
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

# The sweep target is the app's own CACHE_DIR, not a relative ``Path("cache")``.
# A relative default resolves against the working directory, so it deleted
# whichever ``cache`` sat beside wherever the process started -- and because the
# test suite's redirect only rebases paths under a known *absolute* data dir, it
# was the one data path no fixture could steer away from the developer's real
# cache. Absolute, it is redirected with everything else. It also now names the
# directory the app itself fills, which is what a dev-checkout twin of the
# uninstaller is supposed to mean: from a git worktree CACHE_DIR resolves to the
# primary checkout, so the sweep no longer misses the cache that is in use. Same
# defect and same fix as ``LEGACY_CURR_DECK_CACHE`` in 41599b57.
from utils.constants import CACHE_DIR  # noqa: E402

#: ``card_images`` is regenerable but expensive (thousands of downloads).
#: Everything else here is a leftover of the user's own work that nothing can
#: regenerate at all, kept at the path it had *before* it moved beside
#: ``config/``: a history root, a records database, and the three documents a
#: person typed about their decks -- their notes, their outboard lists and their
#: sideboard guides. Each of those moves itself only when the app next opens it
#: (``repositories/deck_repository/migration.py``,
#: ``utils/deck_metadata_migration.py``), and a cache clear is not the place to
#: find out that the move has not happened yet: a checkout that has only ever
#: run the tests has never opened any of them.
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
    "deck_notes.json",
    "deck_outboard.json",
    "deck_sbguides.json",
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
