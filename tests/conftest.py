"""Root-level pytest fixtures for all tests.

This module provides fixtures that are available to all tests in the project.
"""

import pytest
from data_isolation import (
    REAL_DATA_DIRS,
    redirect_bound_paths,
    session_data_dirs,
    snapshot_real_data,
)
from test_helpers import reset_all_globals

from utils.constants import timing


@pytest.fixture(scope="session", autouse=True)
def real_data_untouched():
    """Fail the run if any test wrote to the user's real config/, cache/ or deck folder.

    Snapshots every file under them before the first test and compares after the
    last. It caught test_notebook_tabs_fit overwriting deck_selector_settings.json,
    test_notes_persist_across_frames clearing deck_notes.json, and the radar,
    card-pool and image caches being created by repositories built with their
    real default paths.
    """
    before = snapshot_real_data()
    yield
    after = snapshot_real_data()
    changed = sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
    assert not changed, (
        f"Tests modified the user's real data: {changed[:20]}. Something reached a real "
        "path that tests/data_isolation.py did not redirect. (Running the app at the "
        "same time as the suite also trips this.)"
    )


@pytest.fixture(scope="session", autouse=True)
def redirect_real_data_for_session(real_data_untouched, tmp_path_factory):
    """Redirect every real data path into a session tmp dir for the whole run.

    Depends on the guard so its snapshot is taken first. Per-test isolation
    (tests/ui/conftest.py) layers on top; this layer is what late work lands on,
    e.g. a deck download a UI test left running that reached the deck-text cache
    after that test's patches were undone.
    """
    root = tmp_path_factory.mktemp("mtgo-session")
    roots = {key: root / key for key in REAL_DATA_DIRS}
    for directory in roots.values():
        directory.mkdir(parents=True, exist_ok=True)
    with pytest.MonkeyPatch.context() as session_patch:
        redirect_bound_paths(session_patch, roots)
        session_data_dirs.update(roots)
        try:
            yield
        finally:
            session_data_dirs.clear()


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
