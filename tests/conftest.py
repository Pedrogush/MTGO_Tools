"""Root-level pytest fixtures for all tests.

This module provides fixtures that are available to all tests in the project.
"""

from pathlib import Path

import pytest
from test_helpers import reset_all_globals

from utils.constants import CACHE_DIR, CONFIG_DIR, DECKS_DIR, timing

# Captured at import, before any fixture patches them: the user's real data dirs.
_REAL_DATA_DIRS = (Path(CONFIG_DIR), Path(CACHE_DIR), Path(DECKS_DIR))


def _stat_files(directory: Path) -> dict[str, tuple[int, int]]:
    """``{name: (size, mtime_ns)}`` for the files directly inside *directory*.

    Size and mtime rather than bytes: cache/ holds multi-megabyte databases, and
    every write this guard exists to catch changes the mtime.
    """
    if not directory.is_dir():
        return {}
    stats: dict[str, tuple[int, int]] = {}
    for path in directory.iterdir():
        try:
            if path.is_file():
                info = path.stat()
                stats[path.name] = (info.st_size, info.st_mtime_ns)
        except OSError:
            continue
    return stats


@pytest.fixture(scope="session", autouse=True)
def real_data_untouched():
    """Fail the run if any test wrote to the user's real config/, cache/ or deck folder.

    Tests patch the path constants into tmp dirs, but a module that imported a
    constant by name keeps the real path and writes straight past the patch.
    That is how test_notebook_tabs_fit overwrote deck_selector_settings.json and
    test_notes_persist_across_frames cleared the real deck_notes.json.
    """
    before = {directory: _stat_files(directory) for directory in _REAL_DATA_DIRS}
    yield
    changed = []
    for directory, old in before.items():
        new = _stat_files(directory)
        changed += [
            str(directory / name)
            for name in sorted(old.keys() | new.keys())
            if old.get(name) != new.get(name)
        ]
    assert not changed, (
        f"Tests modified the user's real data: {changed}. A test is writing through a "
        "path imported before it was patched. (Running the app at the same time as the "
        "suite also trips this.)"
    )


@pytest.fixture(autouse=True)
def reset_global_state():
    """Automatically reset all global service and repository instances after each test.

    This fixture ensures test isolation by resetting all singleton instances
    to None after each test completes, preventing state leakage between tests.
    """
    yield
    reset_all_globals()


@pytest.fixture(autouse=True)
def _fast_batch_resolve_debounce(monkeypatch):
    """Collapse the batch-resolver debounce so tests don't wait the real 0.5s.

    The Scryfall batch resolver waits ``IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS`` to
    collect a burst before firing. That window is production behavior, not
    something unit tests should sit through — the resolver reads the constant
    live each window, so patching it here keeps the suite fast. Tests that
    exercise the debounce itself override this locally.
    """
    monkeypatch.setattr(timing, "IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS", 0.0)
