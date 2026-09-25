"""Moving the per-deck metadata stores out of ``cache/``, once, on first use.

``deck_notes.json``, ``deck_outboard.json`` and ``deck_sbguides.json`` shipped
under ``cache/``, which the uninstaller (``[UninstallDelete]`` in
packaging/installer.iss) and ``scripts/clear_caches.py`` both sweep wholesale,
under a comment promising that everything swept there can be refetched or
recomputed on the next run. Nothing recomputes a note a person typed. An
uninstall, a reinstall or a cache clear threw away every deck's notes, outboard
list and sideboard guide while leaving the ``.txt`` files it named as the thing
being kept -- the same failure that moved deck history and the saved-deck
records to ``DECK_RECORDS_DIR``, on three files that audit did not reach.

So the three moved to ``DECK_RECORDS_DIR`` as well, and -- like the records
database, and unlike deck history, which never shipped and so had nothing to
migrate -- installed builds have real files at the old paths. This module moves
them, at most once each, the first time anything asks where they are.

Not in :func:`utils.constants.paths.ensure_base_dirs`, which promises to create
directories "without importing side effects" and runs in processes that never
open these files; and not at import time, for the same reason. Doing it behind
:func:`deck_metadata_stores` means a caller cannot reach the new path without
the move having been attempted first, it happens only in a process that is about
to use the thing, and it covers the opponent tracker -- which reads the guide
store straight off the path, not through the controller -- as well as the app.

These are plain JSON documents rather than a live SQLite database, so the move
is a bare :func:`os.replace` and not the backup-API dance
:mod:`repositories.deck_repository.migration` needs. ``os.replace`` is atomic,
and both paths are children of ``BASE_DATA_DIR``, so the rename never crosses a
volume and never degrades into a copy.

Interruption safety, per file, in the order the branches are taken:

* Nothing at the old path -- the normal case after the first run, and the only
  case for an install that never had one -- is a no-op, which is what makes this
  idempotent and cheap enough to sit in front of every read.
* Both paths populated means an older build wrote the old path again after the
  move. The new document is authoritative and is never touched; the old one is
  *set aside* beside it under a stamped name rather than merged or deleted.
  Merging has no right answer -- the two documents are keyed the same way, so a
  deck with notes in both cannot be reconciled without asking which is wanted --
  and deleting it would be the data loss this whole change exists to prevent.
  Setting it aside gets it out of the swept directory, so it is still there for
  a human, and clears the old path so the next run is a no-op.
* Otherwise the file is renamed. ``os.replace`` either happened or did not:
  interrupted before it, the document is entirely at the old path and the next
  run retries; interrupted after it, it is entirely at the new one and the next
  run is a no-op. There is no staging copy to clean up and no window in which
  the document exists in neither place.

A failure at any point leaves the old file where it is and the app reading an
empty store for this run only -- never a half-written one, because nothing here
writes bytes.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from loguru import logger

from utils.constants import (
    GUIDE_STORE,
    LEGACY_GUIDE_STORE,
    LEGACY_NOTES_STORE,
    LEGACY_OUTBOARD_STORE,
    NOTES_STORE,
    OUTBOARD_STORE,
)


class DeckMetadataStores(NamedTuple):
    """The three per-deck metadata documents, by role."""

    notes: Path
    outboard: Path
    guide: Path


def deck_metadata_stores() -> DeckMetadataStores:
    """The three store paths, with anything left at the old paths moved there first.

    The only supported way to reach these paths. Reading the constants directly
    skips the migration and hands an upgrading user an empty store while their
    real one sits in the directory the next uninstall deletes.
    """
    migrate_deck_metadata_stores()
    return DeckMetadataStores(NOTES_STORE, OUTBOARD_STORE, GUIDE_STORE)


def migrate_deck_metadata_stores() -> bool:
    """Move any of the three stores left at its old path; did anything move?

    Safe to call on every startup and from more than one process: see the module
    docstring for what each branch guarantees. The pairs are built here rather
    than held in a module constant so that the names resolve on every call --
    the test suite redirects these paths by rebinding them on this module.
    """
    moves = (
        (NOTES_STORE, LEGACY_NOTES_STORE),
        (OUTBOARD_STORE, LEGACY_OUTBOARD_STORE),
        (GUIDE_STORE, LEGACY_GUIDE_STORE),
    )
    # Every pair is attempted, so one store that will not move does not strand
    # the other two; ``any(...)`` over a generator would stop at the first True.
    moved = False
    for path, legacy_path in moves:
        moved = _migrate_store(path, legacy_path) or moved
    return moved


def _migrate_store(path: Path, legacy_path: Path) -> bool:
    """Move one store from *legacy_path* to *path*; did anything move?"""
    path, legacy_path = Path(path), Path(legacy_path)
    if not legacy_path.exists():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return _set_aside(path, legacy_path)
        os.replace(legacy_path, path)
    except OSError as exc:
        # Left exactly where it is: the app reads an empty store for this run,
        # and the next run tries again. Nothing has been written or removed.
        logger.warning(f"Could not move deck metadata store {legacy_path} to {path}: {exc}")
        return False
    logger.info(f"Moved deck metadata store from {legacy_path} to {path}")
    return True


def _set_aside(path: Path, legacy_path: Path) -> bool:
    """Keep the superseded *legacy_path* beside *path*, out of the swept directory."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kept = path.with_name(f"{path.stem}.superseded-{stamp}{path.suffix}")
    # ``os.replace`` overwrites, and the stamp has one-second resolution, so two
    # set-asides in the same second would silently leave one file. Step past a
    # name already taken instead; the thing being kept is the only copy there is.
    attempt = 1
    while kept.exists():
        attempt += 1
        kept = path.with_name(f"{path.stem}.superseded-{stamp}-{attempt}{path.suffix}")
    os.replace(legacy_path, kept)
    logger.warning(
        f"{path} already existed, so {legacy_path} was kept as {kept} rather than merged. "
        "The app reads the former; the latter holds whatever an older build wrote."
    )
    return True


__all__ = ["DeckMetadataStores", "deck_metadata_stores", "migrate_deck_metadata_stores"]
