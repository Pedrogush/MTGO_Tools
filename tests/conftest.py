"""Root-level pytest fixtures for all tests.

This module provides fixtures that are available to all tests in the project.
"""

import os
import warnings

import pytest
from data_isolation import (
    REAL_DATA_DIRS,
    normalized,
    real_paths_written_here,
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

    A changed file is only the suite's fault if this process wrote it. The app
    resolves its data dirs to the same checkout the suite runs from, so a
    developer running ``main.py --automation`` (or a second worktree's suite)
    keeps writing the deck and card caches while the run happens; blaming the
    run for that produced an ``ERROR at teardown`` on whichever test happened to
    be last, with a longer run being likelier to catch a write. So the assertion
    covers the paths ``data_isolation``'s audit hook saw this process open for
    writing, and anything else that moved is reported as a warning naming the
    files. CI has no second writer, so there it stays a hard failure -- that is
    also what still covers a write made by a subprocess the suite spawned, which
    the audit hook cannot see.
    """
    before = snapshot_real_data()
    yield
    after = snapshot_real_data()
    changed = sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
    written_here = real_paths_written_here()
    ours = [path for path in changed if normalized(path) in written_here]
    assert not ours, (
        f"Tests modified the user's real data: {ours[:20]}. Something reached a real "
        "path that tests/data_isolation.py did not redirect."
    )
    if changed:  # Nothing here was written by this process; see the docstring.
        message = (
            f"{len(changed)} file(s) under the real data dirs changed during the run, but no "
            f"test process wrote them: {changed[:20]}. Another process on this machine (the "
            "app, or a second checkout's suite) is writing the shared data dirs."
        )
        assert not os.environ.get("CI"), message
        warnings.warn(message, stacklevel=1)


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
    session_patch = pytest.MonkeyPatch()
    redirect_bound_paths(session_patch, roots)
    session_data_dirs.update(roots)
    yield
    # Deliberately never undone. A worker a test left running goes on writing
    # until the interpreter stops -- a deck download landing in the deck-text
    # cache, the radar worker in its database -- and that is *after* every
    # fixture has finished. Undoing this redirect at the end of the session put
    # the real paths back in time for exactly those writes: a run of
    # tests/ui/test_deck_selector.py alone created cache/deck_cache.db in an
    # otherwise untouched data dir. Nothing runs after this point that wants
    # the real paths back; the guard's snapshot reads REAL_DATA_DIRS, which
    # this never patched.


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
