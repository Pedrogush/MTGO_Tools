"""Where deck version history is kept, and what is allowed to delete it.

A deck's edit history is the user's own work: unlike everything else this app
writes, no rescan and no network fetch can bring it back. Two things sweep this
app's data wholesale -- the installer's ``[UninstallDelete]`` section and
``scripts/clear_caches.py`` -- and both promise, in a comment, that what the
user made is preserved. It was not: the repos were rooted under ``cache/``, so
an uninstall deleted every version of every deck while leaving the ``.txt``
files it named as the thing being kept.

Both sweeps are policy written outside Python -- an ``.iss`` section and a
``PRESERVE`` set -- so both are read here rather than restated, and the
directory is read off the repository rather than off a constant. What is under
test is that those three answers still agree.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

import utils.constants as constants
from repositories.deck_vcs_repository import DeckVcsRepository
from scripts import clear_caches
from services.deck_vcs_service import DeckVcsService

DECK = "4 Lightning Bolt\n2 Consider\n\nSideboard\n2 Abrade\n"

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
    """Real ``cache``/``deck_history``/deck directories, with the constants pointed at them.

    ``clear_caches`` resolves ``cache`` relative to the working directory, which
    is how a developer runs it, so the base directory is also where the test
    runs from.
    """
    base = tmp_path / "MTGO Tools"
    dirs = {name: base / name for name in ("cache", "deck_history")}
    dirs["decks"] = tmp_path / "mtgo_decks"
    for directory in dirs.values():
        directory.mkdir(parents=True)
    monkeypatch.setattr(constants, "CACHE_DIR", dirs["cache"])
    monkeypatch.setattr(constants, "DECK_HISTORY_DIR", dirs["deck_history"], raising=False)
    monkeypatch.chdir(base)
    return dirs


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

    clear_caches.clear_caches()

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
