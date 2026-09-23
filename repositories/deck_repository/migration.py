"""Moving the saved-deck database out of ``cache/``, once, on first use.

``saved_decks.db`` shipped under ``cache/``, which the uninstaller
(``[UninstallDelete]`` in packaging/installer.iss) and ``scripts/clear_caches.py``
both sweep wholesale. That was survivable while a row was only a convenience
copy of a ``.txt`` the user still had; it stopped being survivable once the row
started carrying the deck's ``deck_uuid``, because that uuid is the only thing
that names the deck's directory under ``deck_history/``. Sweep the database and
the histories are still on disk and no longer reachable by anything.

So the database moved to ``DECK_RECORDS_DIR``, and -- unlike deck history, which
never shipped and so had nothing to migrate -- installed builds have a real one
at the old path. This module moves it, at most once, the first time anything
asks for the default database path.

Not in :func:`utils.constants.paths.ensure_base_dirs`, which promises to create
directories "without importing side effects" and runs in processes that never
open this database. Doing it where the path is resolved means it happens exactly
once per run, only in a process that is about to use the thing, and it covers the
automation server and the scripts as well as the app.

Interruption safety, in the order the branches are taken:

* Nothing at the old path -- the normal case after the first run -- is a
  no-op, which is what makes this idempotent.
* Both paths populated means the new database is authoritative and is never
  touched. The old one is *set aside* into ``DECK_RECORDS_DIR`` under a stamped
  name rather than merged or deleted: merging two ``decks`` tables has no right
  answer (the ids collide, and one deck saved in both with different content
  cannot be reconciled without asking), and deleting it would be the data loss
  this whole change exists to prevent. Setting it aside gets it out of the
  swept directory, so it is still there for a human, and clears the old path so
  the next run is a no-op.
* Otherwise the database is copied through SQLite's own backup API into a
  staging file, ``os.replace``'d into place, and only then is the original
  removed. A plain file copy would tear a database another process is writing,
  and would leave a hot rollback journal behind; the backup API takes SQLite's
  locks and hands back a consistent database. Interrupted before the replace,
  nothing has moved and only a staging file is left; interrupted after it but
  before the unlink, both paths exist and the next run takes the branch above.
  There is no window in which the rows exist in neither place.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from loguru import logger

#: SQLite writes these beside the database. They are transient for a database in
#: the default (rollback journal) mode, but a crashed writer can leave one, and a
#: journal that outlives its database only confuses the next open.
_SIDECAR_SUFFIXES = ("-journal", "-wal", "-shm")


def migrate_saved_decks_database(db_path: Path, legacy_path: Path) -> bool:
    """Move a database left at *legacy_path* to *db_path*; did anything move?

    Safe to call on every startup and from more than one process: see the module
    docstring for what each branch guarantees.
    """
    db_path, legacy_path = Path(db_path), Path(legacy_path)
    if not legacy_path.exists():
        return False
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        return _set_aside(db_path, legacy_path)

    staged = db_path.with_name(f"{db_path.name}.migrating")
    try:
        _copy_database(legacy_path, staged)
        os.replace(staged, db_path)
    except (sqlite3.Error, OSError) as exc:
        # A database that cannot be read is left exactly where it is: the app
        # starts on an empty one, and the next run sets the unreadable file
        # aside where no sweep can reach it.
        logger.warning(f"Could not migrate saved-deck database from {legacy_path}: {exc}")
        _discard(staged)
        return False

    _discard(legacy_path)
    logger.info(f"Moved saved-deck database from {legacy_path} to {db_path}")
    return True


def _copy_database(source: Path, destination: Path) -> None:
    """Copy *source* to *destination* through SQLite, taking its locks."""
    _discard(destination)
    source_conn = sqlite3.connect(source)
    try:
        destination_conn = sqlite3.connect(destination)
        try:
            source_conn.backup(destination_conn)
        finally:
            destination_conn.close()
    finally:
        source_conn.close()


def _set_aside(db_path: Path, legacy_path: Path) -> bool:
    """Keep the superseded *legacy_path* beside *db_path*, out of the swept directory."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kept = db_path.with_name(f"{db_path.stem}.superseded-{stamp}{db_path.suffix}")
    try:
        shutil.move(os.fspath(legacy_path), os.fspath(kept))
    except OSError as exc:
        logger.warning(f"Could not set aside superseded saved-deck database {legacy_path}: {exc}")
        return False
    logger.warning(
        f"{db_path} already existed, so {legacy_path} was kept as {kept} rather than merged. "
        "The app reads the former; the latter holds whatever an older build saved."
    )
    return True


def _discard(path: Path) -> None:
    """Remove *path* and any SQLite sidecar of it, tolerating a file that will not go."""
    for candidate in (path, *(path.with_name(path.name + s) for s in _SIDECAR_SUFFIXES)):
        try:
            candidate.unlink(missing_ok=True)
        except OSError as exc:
            logger.debug(f"Could not remove {candidate}: {exc}")


__all__ = ["migrate_saved_decks_database"]
