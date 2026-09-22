"""The real-data guard: who it blames, when it fails, and how loudly.

``tests/conftest.py``'s ``real_data_untouched`` fixture fails the run for any
change under config/, cache/ or the deck folder. The app resolves its data dirs
to the same checkout the suite runs from, so a developer running
``main.py --automation`` alongside the suite had its deck cache written mid-run
and the assertion landed as an ``ERROR at teardown`` on whichever test happened
to be last -- reproducibly enough to look like that test's bug, and more likely
the longer the run. The attribution here tells the two apart; it decides what
the message says and whether ``MTGO_TOOLS_ALLOW_CONCURRENT_APP`` can excuse the
change, not whether the run fails.

Nothing here writes the real dirs. The probes call audited events that raise
before the syscall, hand ``_audit_real_writes`` an event directly, or move the
guard's own notion of "real" onto ``tmp_path`` first -- reproducing "a test wiped
config/" for real is the accident this guard exists to prevent.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import warnings

import conftest
import data_isolation
import pytest
from data_isolation import (
    REAL_DATA_DIRS,
    normalized,
    real_paths_written_here,
)

#: The opt-out, spelled out rather than imported: its name is the contract a
#: developer types, so a rename should fail here.
ALLOW_CONCURRENT_APP = "MTGO_TOOLS_ALLOW_CONCURRENT_APP"

_CHILD_WRITE = (
    "import pathlib, sys; pathlib.Path(sys.argv[1]).write_text('child', encoding='utf-8')"
)


@pytest.fixture
def forget_probe_writes():
    """Drop whatever the probe recorded, so the session guard never sees it."""
    recorded: list[str] = []
    yield recorded
    for path in recorded:
        data_isolation._own_real_writes.discard(path)


def test_hook_is_installed_and_records_a_real_data_write(forget_probe_writes):
    """A real audited call against a real data path is attributed to this process.

    ``os.rmdir`` raises its audit event before the syscall, so this proves the
    hook is wired without creating or removing anything.
    """
    target = REAL_DATA_DIRS["cache"] / "data-isolation-guard-probe"
    key = normalized(target)
    forget_probe_writes.append(key)

    with pytest.raises(OSError):
        os.rmdir(target)

    assert key in real_paths_written_here()


def test_reads_are_not_writes(forget_probe_writes):
    target = REAL_DATA_DIRS["config"] / "data-isolation-guard-probe-read.json"
    key = normalized(target)
    forget_probe_writes.append(key)

    data_isolation._audit_real_writes("open", (str(target), "r", None))

    assert key not in real_paths_written_here()


def test_os_open_write_flags_count_as_a_write(forget_probe_writes):
    """``os.open`` reports no mode string, only flags."""
    target = REAL_DATA_DIRS["config"] / "data-isolation-guard-probe-oswrite.json"
    key = normalized(target)
    forget_probe_writes.append(key)

    data_isolation._audit_real_writes("open", (str(target), None, os.O_WRONLY | os.O_CREAT))

    assert key in real_paths_written_here()


def test_writes_outside_the_real_dirs_are_ignored(tmp_path, forget_probe_writes):
    target = tmp_path / "redirected.json"
    key = normalized(target)
    forget_probe_writes.append(key)

    data_isolation._audit_real_writes("open", (str(target), "w", None))

    assert key not in real_paths_written_here()


def test_a_malformed_event_never_raises():
    """An exception in an audit hook propagates into whatever was audited."""
    data_isolation._audit_real_writes("open", ())
    data_isolation._audit_real_writes("os.remove", (None,))
    data_isolation._audit_real_writes("os.rename", (object(),))


@pytest.fixture
def fake_real_dirs(tmp_path, monkeypatch):
    """Move the guard's notion of "real" onto *tmp_path*, and clear the env it reads.

    Everything downstream is the production path: ``snapshot_real_data`` reads
    ``REAL_DATA_DIRS`` at call time, the audit hook matches
    ``_REAL_DIR_PREFIXES``, and the fixture under test is the one the suite runs
    with. Only the directories being guarded are fake, because the condition
    being reproduced is a file under config/ being overwritten.
    """
    roots = {key: tmp_path / key for key in REAL_DATA_DIRS}
    for directory in roots.values():
        directory.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(data_isolation, "REAL_DATA_DIRS", roots)
    monkeypatch.setattr(
        data_isolation,
        "_REAL_DIR_PREFIXES",
        tuple(os.path.join(normalized(directory), "") for directory in roots.values()),
    )
    monkeypatch.delenv(ALLOW_CONCURRENT_APP, raising=False)
    monkeypatch.delenv("CI", raising=False)
    return roots


def _undecorated(fixture):
    """The generator function behind a ``@pytest.fixture``, so a test can drive it."""
    return getattr(fixture, "__wrapped__", fixture)


def _started(fixture, *args):
    """*fixture* run up to its ``yield``; ``next(result, None)`` runs its teardown."""
    generator = _undecorated(fixture)(*args)
    next(generator)
    return generator


def test_a_child_processs_write_is_unattributed_and_still_fails(
    fake_real_dirs, forget_probe_writes
):
    """A subprocess wiping a real file fails the run, off CI, with no env set.

    ``sys.addaudithook`` is per-process and blind to a child, and this suite
    spawns real ones: the bridge session's launcher, the bridge client's stubs,
    ``git`` in the version tests, pytest itself under ``run_tests_fast``. While
    an unattributed change was only a warning off CI, a child that overwrote
    config/ printed one line into the summary and the run went green.
    """
    # Created rather than overwritten: the snapshot compares (size, mtime) and
    # cannot tell the two apart, and seeding it here would be a write by *this*
    # process, which is the attribution the test needs to stay clear of.
    target = fake_real_dirs["config"] / "deck_selector_settings.json"
    forget_probe_writes.append(normalized(target))
    guard = _started(conftest.real_data_untouched)

    subprocess.run([sys.executable, "-c", _CHILD_WRITE, str(target)], check=True)

    assert target.read_text(encoding="utf-8") == "child"
    assert normalized(target) not in real_paths_written_here(), "the hook saw a child's write"
    with pytest.raises(AssertionError, match="deck_selector_settings"):
        next(guard, None)


def test_a_write_from_this_process_says_so(fake_real_dirs, forget_probe_writes):
    """The attribution still runs -- it picks the message, not the verdict."""
    target = fake_real_dirs["cache"] / "deck_cache.json"
    forget_probe_writes.append(normalized(target))
    guard = _started(conftest.real_data_untouched)

    target.write_text("written by the suite", encoding="utf-8")

    assert normalized(target) in real_paths_written_here()
    with pytest.raises(AssertionError, match="did not redirect"):
        next(guard, None)


def test_the_concurrent_app_opt_out_downgrades_it_to_a_warning(
    fake_real_dirs, forget_probe_writes, monkeypatch
):
    """The developer who knows the app is running says so and gets a warning.

    This is the case the hard default costs: the app writes the deck cache
    underneath a run that did nothing wrong. It has to be opted into per run,
    because the guard cannot tell it apart from a subprocess of the suite.
    """
    target = fake_real_dirs["cache"] / "deck_cache.db"
    forget_probe_writes.append(normalized(target))
    monkeypatch.setenv(ALLOW_CONCURRENT_APP, "1")
    guard = _started(conftest.real_data_untouched)

    subprocess.run([sys.executable, "-c", _CHILD_WRITE, str(target)], check=True)

    with pytest.warns(UserWarning, match="deck_cache.db"):
        next(guard, None)


def test_ci_is_not_excused_by_the_opt_out(fake_real_dirs, forget_probe_writes, monkeypatch):
    """CI has no second app to blame, so the excuse does not apply there."""
    target = fake_real_dirs["cache"] / "deck_cache.db"
    forget_probe_writes.append(normalized(target))
    monkeypatch.setenv(ALLOW_CONCURRENT_APP, "1")
    monkeypatch.setenv("CI", "1")
    guard = _started(conftest.real_data_untouched)

    subprocess.run([sys.executable, "-c", _CHILD_WRITE, str(target)], check=True)

    with pytest.raises(AssertionError, match="deck_cache.db"):
        next(guard, None)


def test_an_untouched_run_is_silent(fake_real_dirs):
    """No change, no message -- the guard is autouse on every run."""
    guard = _started(conftest.real_data_untouched)

    with warnings.catch_warnings():
        warnings.simplefilter("error")
        next(guard, None)


def test_the_per_test_guard_names_the_test_that_wrote(fake_real_dirs, forget_probe_writes, request):
    """Blame lands on a test, while its name is still on screen.

    The session guard reports at the end of the run and ``_own_real_writes``
    carries no test names, so its message can only say that *something* in the
    run wrote a real path.
    """
    target = fake_real_dirs["config"] / "deck_notes.json"
    forget_probe_writes.append(normalized(target))
    guard = _started(conftest._name_the_test_that_wrote_real_data, request)

    data_isolation._audit_real_writes("open", (str(target), "w", None))

    with pytest.raises(AssertionError, match=re.escape(request.node.nodeid)):
        next(guard, None)


def test_the_per_test_guard_leaves_the_session_guard_its_evidence(
    fake_real_dirs, forget_probe_writes, request
):
    """It diffs the set; clearing it would blind the session guard's attribution."""
    target = fake_real_dirs["config"] / "deck_notes.json"
    key = normalized(target)
    forget_probe_writes.append(key)
    guard = _started(conftest._name_the_test_that_wrote_real_data, request)

    data_isolation._audit_real_writes("open", (str(target), "w", None))
    with pytest.raises(AssertionError):
        next(guard, None)

    assert key in real_paths_written_here()


def test_the_per_test_guard_ignores_writes_from_before_it_started(
    fake_real_dirs, forget_probe_writes, request
):
    """Only what this test added counts, or every test after the first fails."""
    earlier = fake_real_dirs["config"] / "written-by-an-earlier-test.json"
    forget_probe_writes.append(normalized(earlier))
    data_isolation._audit_real_writes("open", (str(earlier), "w", None))

    guard = _started(conftest._name_the_test_that_wrote_real_data, request)

    next(guard, None)

