"""``pytest tests/ui`` must not write into the developer's real ``cache/`` directory.

The autouse ``ui_environment`` fixture redirects a list of path constants with
``monkeypatch.setattr(constants, NAME, ...)``. That only reaches consumers which
resolve ``constants.NAME`` at call time — and almost none do, so most of that list
is inert (see the comment on ``replacements`` in ``tests/ui/conftest.py``). Two of
the leaks were real writes into the checkout: the SQLite deck cache
(``cache/deck_cache.db``) and the metagame JSON caches (``cache/archetype_list.json``,
``cache/archetype_decks_cache.json``).

These tests pin the fix. They build a real ``AppFrame`` the way every other UI test
does, drive the production accessors, and then assert the *real* files on disk were
not touched — by fingerprint ``(st_mtime_ns, st_size)`` including SQLite's ``-wal``
and ``-shm`` sidecars, and by reading the real DB back to prove the probe row is
absent. The real DB is opened with ``immutable=1`` so the check cannot itself create
a ``-wal``/``-shm`` pair and invalidate its own fingerprint.
"""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path
from urllib.parse import quote

import pytest

wx = pytest.importorskip("wx")

import repositories.metagame_repository as metagame_repository  # noqa: E402
from repositories.deck_text_cache import get_deck_cache  # noqa: E402
from utils.constants.paths import (  # noqa: E402
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    DECK_CACHE_DB_FILE,
)

# Imported from ``utils.constants.paths`` (not ``utils.constants``) and bound at
# module import, i.e. before ``ui_environment`` runs: these are deliberately the
# real, un-redirected locations under the developer's checkout.
REAL_DECK_DB = DECK_CACHE_DB_FILE
REAL_ARCHETYPE_LIST = ARCHETYPE_LIST_CACHE_FILE
REAL_ARCHETYPE_DECKS = ARCHETYPE_DECKS_CACHE_FILE


def _fingerprint(path: Path) -> tuple[int, int] | None:
    """Return ``(mtime_ns, size)`` for *path*, or ``None`` when it does not exist."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _fingerprints(paths: list[Path]) -> dict[Path, tuple[int, int] | None]:
    return {path: _fingerprint(path) for path in paths}


def _with_sidecars(db_path: Path) -> list[Path]:
    """The DB plus the WAL/SHM files SQLite writes alongside it."""
    return [
        db_path,
        db_path.with_name(f"{db_path.name}-wal"),
        db_path.with_name(f"{db_path.name}-shm"),
    ]


def _probe_row_in_real_db(db_path: Path, deck_number: str) -> bool:
    """Read the real deck cache without touching it.

    ``immutable=1`` promises SQLite the file cannot change, so it opens read-only
    and creates no journal, WAL, or SHM file — otherwise the act of checking would
    perturb the very fingerprints this module asserts on.
    """
    if not db_path.exists():
        return False
    uri = f"file:{quote(db_path.as_posix(), safe='/:')}?immutable=1"
    try:
        with sqlite3.connect(uri, uri=True) as conn:
            rows = conn.execute(
                "SELECT 1 FROM deck_cache WHERE deck_number = ?", (deck_number,)
            ).fetchall()
    except sqlite3.DatabaseError:
        # No such table / unreadable file: the probe certainly is not in there.
        return False
    return bool(rows)


def test_ui_fixtures_keep_the_real_deck_cache_db_untouched(deck_selector_factory) -> None:
    """A UI test writing through ``get_deck_cache()`` must miss the real DB entirely."""
    watched = _with_sidecars(REAL_DECK_DB)
    before = _fingerprints(watched)

    frame = deck_selector_factory()
    try:
        # A fresh id every run, so a stale row from an earlier run plus
        # ``INSERT OR REPLACE``/``OR IGNORE`` semantics cannot mask a leak.
        probe_number = f"ui-isolation-probe-{uuid.uuid4().hex}"
        probe_text = "4 Mountain\n4 Island\n"

        cache = get_deck_cache()
        assert cache.set(probe_number, probe_text) is True
        assert cache.get(probe_number) == probe_text

        assert not _probe_row_in_real_db(REAL_DECK_DB, probe_number)
        assert _fingerprints(watched) == before
        assert cache.db_path != REAL_DECK_DB
    finally:
        frame.Destroy()


def test_ui_fixtures_keep_the_real_metagame_caches_untouched(
    deck_selector_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A UI test refreshing archetypes must write its JSON cache under ``tmp_path``."""
    watched = [REAL_ARCHETYPE_LIST, REAL_ARCHETYPE_DECKS]
    before = _fingerprints(watched)

    probe = f"ui-isolation-probe-{uuid.uuid4().hex}"
    # A format name no real cache file will ever hold, so even a regression writes
    # a junk key rather than clobbering the developer's cached "modern" entry.
    probe_format = f"__{probe}__"

    # Keep the refresh off the network: no remote snapshot, and a local stand-in
    # for the MTGGoldfish scrape (the one category tests/README.md §2 allows faking).
    monkeypatch.setattr(metagame_repository, "REMOTE_SNAPSHOTS_ENABLED", False, raising=False)
    monkeypatch.setattr(
        metagame_repository,
        "get_archetypes",
        lambda mtg_format: [{"name": probe, "href": probe}],
        raising=False,
    )

    frame = deck_selector_factory()
    try:
        repo = metagame_repository.get_metagame_repository()
        # The frame really is backed by the isolated instance, not a second one.
        assert frame.metagame_repo is repo

        # force_refresh skips the cache read so the resolver reaches the save path.
        assert repo.get_archetypes_for_format(probe_format, force_refresh=True) == [
            {"name": probe, "href": probe}
        ]
        assert probe in repo.archetype_list_cache_file.read_text(encoding="utf-8")

        for path in watched:
            if path.exists():
                assert probe not in path.read_text(encoding="utf-8", errors="ignore")
        assert _fingerprints(watched) == before
        assert repo.archetype_list_cache_file != REAL_ARCHETYPE_LIST
        assert repo.archetype_decks_cache_file != REAL_ARCHETYPE_DECKS
    finally:
        frame.Destroy()
