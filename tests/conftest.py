"""Root-level pytest fixtures for all tests.

This module provides fixtures that are available to all tests in the project.
"""

import warnings

import pytest
from data_isolation import (
    REAL_DATA_DIRS,
    guard_verdict,
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

    Any change is a failure. ``data_isolation``'s audit hook says which of them
    this process wrote, and the message names that case separately, but the
    verdict is the same: the data is already gone by the time the guard reads
    the snapshot, so the run has to stop loudly either way.

    The one excuse is a second writer the developer knows about. The app
    resolves its data dirs to the same checkout the suite runs from, so
    ``main.py --automation`` (or a second worktree's suite) keeps writing the
    deck and card caches while the run happens, and blaming the run for that
    produced an ``ERROR at teardown`` on whichever test happened to be last.
    Setting ``MTGO_TOOLS_ALLOW_CONCURRENT_APP=1`` downgrades an unattributed
    change to a warning for that run.

    Attribution was briefly the *default* instead -- hard failure only for paths
    the hook saw, a warning otherwise unless ``CI`` was set. That is backwards:
    ``sys.addaudithook`` is per-process and blind to a child, and this suite
    spawns real ones (the bridge session's launcher, the bridge client's stubs,
    ``git`` in the version tests, pytest itself under
    ``scripts/run_tests_fast.py``). A subprocess wiping config/ warned on the
    machine that had data to lose and failed only on CI, which had none.
    """
    before = snapshot_real_data()
    yield
    after = snapshot_real_data()
    changed = sorted(
        path for path in before.keys() | after.keys() if before.get(path) != after.get(path)
    )
    verdict = guard_verdict(changed, real_paths_written_here())
    if verdict:
        message, fatal = verdict
        assert not fatal, message
        warnings.warn(message, stacklevel=1)  # Excused by ALLOW_CONCURRENT_APP_ENV.


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
def _name_the_test_that_wrote_real_data(request):
    """Fail the test that reached a real data path, while its name is still known.

    ``real_data_untouched`` is session-scoped: it reports at the end of the run,
    by which point the file has been overwritten and ``_own_real_writes`` is a
    pile with no test names in it, so finding the culprit means bisecting the
    run. This diffs the same set across each test instead, so ``-x`` stops on the
    write rather than after it, and on the test that made it.

    Declared before the other function-scoped autouse fixtures so it tears down
    last and still sees what they write on their way out. It deliberately does
    not clear ``_own_real_writes``: the session guard needs the whole run's
    writes to attribute what its snapshot found, and a test that fails here
    fails the run anyway.
    """
    before = real_paths_written_here()
    yield
    written = sorted(real_paths_written_here() - before)
    assert not written, (
        f"{request.node.nodeid} wrote the user's real data: {written[:20]}. It reached a "
        "real path that tests/data_isolation.py did not redirect."
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
