"""Where a deck's history, records and metadata are kept, and what may delete them.

A deck's edit history, the record that names it, and the notes, outboard list
and sideboard guide the user typed about it are the user's own work: unlike
everything else this app writes, no rescan and no network fetch can bring them
back. Two things sweep this app's data wholesale -- the installer's
``[UninstallDelete]`` section and ``scripts/clear_caches.py`` -- and both
promise, in a comment, that what the user made is preserved. Neither did: the
per-deck git repos, ``saved_decks.db`` and all three metadata documents sat
under ``cache/``, so an uninstall deleted every version of every deck and every
note about it while leaving the ``.txt`` files it named as the thing being kept.

They are one subject rather than three, which is why they are tested in one
place. A history is keyed by the ``deck_uuid`` on the deck's record and by
nothing else, so the record surviving a sweep is what makes the history that
survived it reachable; moving only one of them out of ``cache/`` would have left
the histories on disk with nothing able to name them. The three JSON stores were
found by the review of the fix for the other two, in the same directory, under
the comment that fix had just added promising the directory held nothing a
person had authored.

Both sweeps are policy written outside Python -- an ``.iss`` section and a
``PRESERVE`` set -- so both are read here rather than restated, and the
directories are read off the repositories rather than off a constant. What is
under test is that those answers still agree.
"""

from __future__ import annotations

import gc
import json
import os
import re
from pathlib import Path

import pytest
from data_isolation import REAL_DATA_DIRS, redirect_bound_paths

import utils.constants as constants
from repositories.deck_repository import DeckRepository
from repositories.deck_vcs_repository import DeckVcsRepository
from scripts import clear_caches
from services.deck_vcs_service import DeckVcsService
from utils.deck_metadata_migration import deck_metadata_stores, migrate_deck_metadata_stores

DECK = "4 Lightning Bolt\n2 Consider\n\nSideboard\n2 Abrade\n"

#: The three documents a person types about a deck, in the order
#: :func:`deck_metadata_stores` returns them. File names rather than the
#: constants, so a constant quietly pointed back at ``cache/`` fails the tests
#: below instead of being restated by them.
METADATA_STORE_FILES = ("deck_notes.json", "deck_outboard.json", "deck_sbguides.json")

#: The ``%LOCALAPPDATA%\\<app>`` subdirectories the uninstaller sweeps, and the
#: constant naming each one. Kept as a mapping rather than a list so the parse
#: below is pinned against something, and so a directory added to the installer
#: has to be accounted for here.
SWEPT_DIRECTORIES = {
    "cache": "CACHE_DIR",
    "logs": "LOGS_DIR",
    "data": "CARD_DATA_DIR",
}

_INSTALLER = Path(__file__).resolve().parent.parent / "packaging" / "installer.iss"
_APP_DATA_PREFIX = r"{localappdata}\{#MyAppName}" + "\\"


def _is_at_or_under(value: Path, directory: Path) -> bool:
    child = os.path.normcase(os.fspath(value))
    parent = os.path.normcase(os.fspath(directory))
    return child == parent or child.startswith(parent.rstrip(os.sep) + os.sep)


def _swept_app_data_directories() -> set[str]:
    """The first path segment of every ``[UninstallDelete]`` entry under the app's data dir."""
    text = _INSTALLER.read_text(encoding="utf-8-sig")
    section = text.split("[UninstallDelete]", 1)[1].split("\n[", 1)[0]
    swept = set()
    for name in re.findall(r'Name:\s*"([^"]+)"', section):
        if name.startswith(_APP_DATA_PREFIX):
            swept.add(name[len(_APP_DATA_PREFIX) :].split("\\", 1)[0])
    return swept


@pytest.fixture
def data_dirs(tmp_path, monkeypatch):
    """One tmp directory per real data dir, with every path constant pointed at them.

    Through ``redirect_bound_paths`` rather than a list of ``setattr`` calls, for
    the reason this whole module exists: a constant restated here is a constant
    that cannot move. Redirecting the real layout instead means a file put back
    under ``cache/`` lands in *this* ``cache/`` too, and the sweep below takes
    it -- which is the failure these tests are for. It also reaches the two
    paths ``repositories.deck_repository.database`` imported by name, which
    patching ``utils.constants`` alone would not.

    The sweep is then handed ``dirs["cache"]`` at every call site rather than
    left to its default. A test that takes the default sweeps the real cache
    directory, and ``shutil.rmtree`` over a developer's own data is a loss the
    teardown audit can only name afterwards, never prevent -- so the argument is
    the guard, and no fixture ordering or working directory stands in for it.
    """
    base = tmp_path / "MTGO Tools"
    dirs = {key: base / key for key in REAL_DATA_DIRS}
    # The deck folder is the user's Documents, not app data; keep it off the
    # base directory so nothing here can pass by sitting next to the caches.
    dirs["decks"] = tmp_path / "mtgo_decks"
    for directory in dirs.values():
        directory.mkdir(parents=True)
    redirect_bound_paths(monkeypatch, dirs)
    return dirs


def _record_deck(deck_uuid: str, *, name: str = "Mono Red", db_path=None) -> None:
    """Save one deck record, through the repository that owns the database.

    The collect is not ceremony. ``DatabaseMixin`` opens each connection in a
    ``with`` block, and SQLite's context manager commits without closing, so the
    handle lives until the collector takes it -- and on Windows an open handle
    is what stops a file being moved. The app never notices, because the
    migration runs before anything has connected; a test that seeds the old path
    on purpose does, and would otherwise fail on the machine it was written on.
    """
    DeckRepository(db_path=db_path).save_to_db(
        deck_name=name, deck_content=DECK, deck_uuid=deck_uuid
    )
    gc.collect()


def _superseded_databases(directory: Path) -> list[Path]:
    return sorted(directory.glob("saved_decks.superseded-*.db"))


def test_clearing_the_caches_keeps_the_deck_and_the_versions_of_it(data_dirs):
    """The promise in both sweeps' comments, asserted against the real script.

    The deck file surviving is the part that always worked, and is why the loss
    was silent: after an uninstall and reinstall every deck is still there and
    every version of it is gone.
    """
    deck_file = data_dirs["decks"] / "Mono Red.txt"
    deck_file.write_text(DECK, encoding="utf-8")
    history = DeckVcsService(vcs_repo=DeckVcsRepository())
    sha = history.record_save("a-deck-id", DECK)
    regenerable = data_dirs["cache"] / "archetype_cache.json"
    regenerable.write_text("{}", encoding="utf-8")

    clear_caches.clear_caches(data_dirs["cache"])

    assert not regenerable.exists(), "the sweep did not run, so this proves nothing"
    assert deck_file.exists()
    assert [node.sha for node in history.build_graph("a-deck-id")] == [sha]


def test_the_uninstaller_sweeps_exactly_the_regenerable_directories():
    """Pins the parse below, and makes a new swept directory a decision, not a diff."""
    assert _swept_app_data_directories() == set(SWEPT_DIRECTORIES)


def test_no_directory_the_uninstaller_sweeps_contains_the_deck_repos():
    """The installer half of the same promise, against the root the repos really use."""
    vcs_root = DeckVcsRepository()._vcs_root

    for name, constant in SWEPT_DIRECTORIES.items():
        directory = Path(getattr(constants, constant))
        assert not _is_at_or_under(vcs_root, directory), (
            f"deck history is rooted at {vcs_root}, inside {name}, which "
            f"[UninstallDelete] removes on uninstall"
        )


def test_clearing_the_caches_keeps_the_saved_deck_records(data_dirs):
    """The other half of the same promise: the records, not just the .txt files.

    A record is the only place a deck's format, archetype and stable id are
    written down. Rebuilding one from the ``.txt`` is not possible -- the file
    holds a card list and nothing else.
    """
    _record_deck("a-deck-id")
    regenerable = data_dirs["cache"] / "archetype_cache.json"
    regenerable.write_text("{}", encoding="utf-8")

    clear_caches.clear_caches(data_dirs["cache"])

    assert not regenerable.exists(), "the sweep did not run, so this proves nothing"
    assert [deck["name"] for deck in DeckRepository().get_decks()] == ["Mono Red"]


def test_a_cache_clear_leaves_every_history_still_reachable(data_dirs):
    """The point of moving both: a history is only findable through its record.

    Read back the way the app does it -- the record first, then the history
    keyed by the id on it -- so a sweep that took either one would fail here
    even though the other's files are untouched.
    """
    history = DeckVcsService(vcs_repo=DeckVcsRepository())
    sha = history.record_save("a-deck-id", DECK)
    _record_deck("a-deck-id")

    clear_caches.clear_caches(data_dirs["cache"])

    (record,) = DeckRepository().get_decks()
    assert record["deck_uuid"] == "a-deck-id"
    assert [node.sha for node in history.build_graph(record["deck_uuid"])] == [sha]


def test_no_directory_the_uninstaller_sweeps_contains_the_deck_records():
    """The installer half, against the database path the repository really opens."""
    db_path = DeckRepository()._get_db_path()

    for name, constant in SWEPT_DIRECTORIES.items():
        directory = Path(getattr(constants, constant))
        assert not _is_at_or_under(db_path, directory), (
            f"the saved-deck records are at {db_path}, inside {name}, which "
            f"[UninstallDelete] removes on uninstall"
        )


def test_a_database_left_at_the_old_path_moves_itself(data_dirs):
    """Deck records shipped, so unlike deck history they have to be migrated.

    Asserted through ``DeckRepository`` rather than the migration function: what
    is under test is that a user who upgrades still sees their decks, which
    needs the move *and* the resolution of the default path to agree.
    """
    legacy = data_dirs["cache"] / "saved_decks.db"
    _record_deck("a-deck-id", name="Older Build", db_path=legacy)

    decks = DeckRepository().get_decks()

    assert [deck["name"] for deck in decks] == ["Older Build"]
    assert [deck["deck_uuid"] for deck in decks] == ["a-deck-id"]
    assert (data_dirs["deck_records"] / "saved_decks.db").exists()
    assert not legacy.exists(), "the old path must be cleared, or the move runs forever"


def test_migrating_a_second_time_does_nothing(data_dirs):
    """Idempotent, because it runs on every startup and most startups have no work."""
    legacy = data_dirs["cache"] / "saved_decks.db"
    _record_deck("a-deck-id", name="Older Build", db_path=legacy)
    assert [deck["name"] for deck in DeckRepository().get_decks()] == ["Older Build"]
    migrated = data_dirs["deck_records"] / "saved_decks.db"
    before = migrated.stat().st_mtime_ns

    assert [deck["name"] for deck in DeckRepository().get_decks()] == ["Older Build"]

    assert migrated.stat().st_mtime_ns == before
    assert _superseded_databases(data_dirs["deck_records"]) == []


def test_a_database_at_both_paths_keeps_the_new_one_and_sets_the_old_one_aside(data_dirs):
    """Both populated means an older build wrote to the old path after the move.

    Merging the two ``decks`` tables has no right answer and deleting either is
    the data loss this change exists to prevent, so the new database is left
    authoritative and the old one is kept, out of the swept directory, for a
    human to look at.
    """
    legacy = data_dirs["cache"] / "saved_decks.db"
    _record_deck("old-deck-id", name="Older Build", db_path=legacy)
    # Seeded by path, not through the default: resolving the default is what
    # runs the migration, and doing it here would migrate before there was
    # anything at the new path to collide with.
    _record_deck(
        "new-deck-id", name="Newer Build", db_path=data_dirs["deck_records"] / "saved_decks.db"
    )

    decks = DeckRepository().get_decks()

    assert [deck["name"] for deck in decks] == ["Newer Build"]
    assert not legacy.exists()
    (kept,) = _superseded_databases(data_dirs["deck_records"])
    assert [deck["name"] for deck in DeckRepository(db_path=kept).get_decks()] == ["Older Build"]


# ---------------------------------------------------------------------------
# The three documents the user types about a deck
# ---------------------------------------------------------------------------


def _typed(marker: str) -> dict[str, str]:
    """A store document, standing in for whatever the user actually wrote."""
    return {"a-deck": marker}


def _write_store(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_typed(marker)), encoding="utf-8")


def _read_store(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def _superseded_metadata_stores(directory: Path) -> list[Path]:
    return sorted(directory.glob("deck_notes.superseded-*.json"))


def test_the_metadata_stores_are_named_and_ordered_as_this_module_assumes(data_dirs):
    """Pins the accessor's shape, so every assertion below means what it says."""
    stores = deck_metadata_stores()

    assert tuple(path.name for path in stores) == METADATA_STORE_FILES
    assert [path.parent for path in stores] == [data_dirs["deck_records"]] * 3


def test_no_directory_the_uninstaller_sweeps_contains_the_metadata_stores():
    """The installer half of the promise, against the paths the app really opens.

    Read off :func:`deck_metadata_stores` rather than the constants for the same
    reason the two tests above read off the repositories: the accessor is what
    production calls, and a constant moved back under ``cache/`` has to fail
    here rather than be quietly agreed with.
    """
    for path in deck_metadata_stores():
        for name, constant in SWEPT_DIRECTORIES.items():
            directory = Path(getattr(constants, constant))
            assert not _is_at_or_under(path, directory), (
                f"{path.name} is at {path}, inside {name}, which "
                f"[UninstallDelete] removes on uninstall"
            )


def test_clearing_the_caches_keeps_what_the_user_typed_about_a_deck(data_dirs):
    """Notes, outboard lists and sideboard guides are typing, not cache.

    All three sat under ``cache/`` until they moved, so a cache clear -- and the
    uninstall it is the twin of -- threw away every note a user had written
    while keeping the ``.txt`` file it named as the thing being saved. Nothing
    recomputes a note, so the loss was both total and silent.
    """
    stores = deck_metadata_stores()
    for path in stores:
        _write_store(path, "typed by hand")
    regenerable = data_dirs["cache"] / "archetype_cache.json"
    regenerable.write_text("{}", encoding="utf-8")

    clear_caches.clear_caches(data_dirs["cache"])

    assert not regenerable.exists(), "the sweep did not run, so this proves nothing"
    assert [_read_store(path) for path in stores] == [_typed("typed by hand")] * 3


def test_clearing_the_caches_keeps_a_store_that_has_not_migrated_yet(data_dirs):
    """A checkout that has never opened the app still has all three under ``cache/``.

    The move happens on first use and a cache clear is not a use, so ``PRESERVE``
    has to name the old paths as well as leave the new ones alone -- exactly as
    it does for ``deck_vcs`` and ``saved_decks.db``.
    """
    for name in METADATA_STORE_FILES:
        _write_store(data_dirs["cache"] / name, "not migrated yet")
    regenerable = data_dirs["cache"] / "archetype_cache.json"
    regenerable.write_text("{}", encoding="utf-8")

    clear_caches.clear_caches(data_dirs["cache"])

    assert not regenerable.exists(), "the sweep did not run, so this proves nothing"
    assert [_read_store(data_dirs["cache"] / name) for name in METADATA_STORE_FILES] == [
        _typed("not migrated yet")
    ] * 3


def test_a_metadata_store_left_at_the_old_path_moves_itself(data_dirs):
    """The three shipped under ``cache/``, so an upgrading user has real files there.

    Asserted one store at a time because that is the real shape of an upgrade:
    a user with notes but no sideboard guide must not have an empty guide file
    invented for them.
    """
    legacy = data_dirs["cache"] / "deck_notes.json"
    _write_store(legacy, "written by an older build")

    stores = deck_metadata_stores()

    assert _read_store(stores.notes) == _typed("written by an older build")
    assert not legacy.exists(), "the old path must be cleared, or the move runs forever"
    assert not stores.outboard.exists()
    assert not stores.guide.exists()


def test_migrating_the_metadata_stores_with_nothing_to_move_creates_nothing(data_dirs):
    """The normal case, on every startup after the first: three ``exists()`` and out."""
    assert migrate_deck_metadata_stores() is False
    assert [
        name for name in METADATA_STORE_FILES if (data_dirs["deck_records"] / name).exists()
    ] == []


def test_migrating_the_metadata_stores_a_second_time_does_nothing(data_dirs):
    """Idempotent, because it runs in front of every read and most reads have no work."""
    _write_store(data_dirs["cache"] / "deck_notes.json", "written by an older build")
    stores = deck_metadata_stores()
    assert _read_store(stores.notes) == _typed("written by an older build")

    assert migrate_deck_metadata_stores() is False

    assert _read_store(stores.notes) == _typed("written by an older build")
    assert _superseded_metadata_stores(data_dirs["deck_records"]) == []


def test_a_metadata_store_at_both_paths_keeps_the_new_one_and_sets_the_old_one_aside(data_dirs):
    """Both populated means an older build wrote the old path again after the move.

    The two documents are keyed the same way, so a deck with notes in both
    cannot be merged without asking which set is wanted, and deleting either is
    the data loss this change exists to prevent. The new one stays authoritative
    and the old one is kept beside it, out of the swept directory, for a human.
    """
    legacy = data_dirs["cache"] / "deck_notes.json"
    _write_store(legacy, "older build")
    _write_store(data_dirs["deck_records"] / "deck_notes.json", "newer build")

    stores = deck_metadata_stores()

    assert _read_store(stores.notes) == _typed("newer build")
    assert not legacy.exists()
    (kept,) = _superseded_metadata_stores(data_dirs["deck_records"])
    assert _read_store(kept) == _typed("older build")
