"""The real-data guard must blame this process, and only this process.

``tests/conftest.py``'s ``real_data_untouched`` fixture used to fail the run for
*any* change under config/, cache/ or the deck folder. The app resolves its data
dirs to the same checkout the suite runs from, so a developer running
``main.py --automation`` alongside the suite had its deck cache written mid-run
and the assertion landed as an ``ERROR at teardown`` on whichever test happened
to be last -- reproducibly enough to look like that test's bug, and more likely
the longer the run. These pin the attribution that tells the two apart.
"""

from __future__ import annotations

import os

import data_isolation
import pytest
from data_isolation import REAL_DATA_DIRS, normalized, real_paths_written_here


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
