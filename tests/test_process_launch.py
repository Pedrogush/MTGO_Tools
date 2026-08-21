"""Recognising the launches Windows refused (issue: "CreateProcess failed; code 4551").

The whole module is a lookup, so what is worth pinning is not that 4551 maps to
something -- it is the two ways the lookup can be wrong in production. Claiming
a block that did not happen sends the user to Windows Security over an ordinary
missing file; missing a real one puts ``[WinError 4551]`` in front of somebody
who then files a bug against the installer.

Runs on Linux, where ``OSError.winerror`` does not exist: the errors are
constructed with the attribute set by hand, which is also what proves the
``getattr`` guard is doing its job.
"""

from __future__ import annotations

import pytest

from utils.process_launch import (
    ANTIVIRUS,
    APP_CONTROL,
    BLOCKED_WINERRORS,
    GROUP_POLICY,
    HELP_URL,
    describe_launch_block,
    launch_block_reason,
)


def _oserror(winerror: int | None) -> OSError:
    """An ``OSError`` shaped like the one Windows raises, buildable on Linux."""
    exc = OSError("CreateProcess failed")
    if winerror is not None:
        exc.winerror = winerror  # type: ignore[attr-defined]
    return exc


def test_4551_is_recognised_as_an_application_control_block() -> None:
    """The reported code. ERROR_SYSTEM_INTEGRITY_POLICY_VIOLATION."""
    assert launch_block_reason(_oserror(4551)) == APP_CONTROL


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        (225, ANTIVIRUS),  # ERROR_VIRUS_INFECTED
        (226, ANTIVIRUS),  # ERROR_VIRUS_DELETED
        (1260, GROUP_POLICY),  # ERROR_ACCESS_DISABLED_BY_POLICY
        (4550, APP_CONTROL),  # ERROR_SYSTEM_INTEGRITY_ROLLBACK_DETECTED
        (4551, APP_CONTROL),  # ERROR_SYSTEM_INTEGRITY_POLICY_VIOLATION
        (4552, APP_CONTROL),  # ERROR_SYSTEM_INTEGRITY_INVALID_POLICY
        (4553, APP_CONTROL),  # ERROR_SYSTEM_INTEGRITY_POLICY_NOT_SIGNED
    ],
)
def test_each_refusal_code_keeps_its_own_reason(code: int, reason: str) -> None:
    """The numbers are the contract; a typo in one is otherwise invisible."""
    assert launch_block_reason(_oserror(code)) == reason


@pytest.mark.parametrize(
    "code",
    [
        2,  # ERROR_FILE_NOT_FOUND -- a genuinely missing executable
        5,  # ERROR_ACCESS_DENIED -- permissions, not policy
        193,  # ERROR_BAD_EXE_FORMAT -- a 32/64-bit mismatch
        740,  # ERROR_ELEVATION_REQUIRED
        4554,  # a malformed *policy*, not a blocked *file*
    ],
)
def test_ordinary_failures_are_not_dressed_up_as_policy_blocks(code: int) -> None:
    assert launch_block_reason(_oserror(code)) is None


def test_an_error_without_a_winerror_is_not_a_block() -> None:
    """POSIX, and the tests themselves: no attribute must not raise."""
    assert launch_block_reason(_oserror(None)) is None
    assert launch_block_reason(RuntimeError("boom")) is None


def test_a_non_integer_winerror_is_not_a_block() -> None:
    """Nothing promises the attribute is an int; a dict lookup on a str would
    quietly return None anyway, but an unhashable one would raise."""
    exc = OSError("odd")
    exc.winerror = ["4551"]  # type: ignore[attr-defined]
    assert launch_block_reason(exc) is None


def test_the_description_names_what_was_blocked_and_where_to_go() -> None:
    message = describe_launch_block(_oserror(4551), target="the MTGO Tools installer")
    assert message is not None
    assert "the MTGO Tools installer" in message
    assert HELP_URL in message
    # The point of the sentence: the install is fine, the launch is not.
    assert "installed correctly" in message


def test_the_description_is_none_for_an_ordinary_failure() -> None:
    """So callers can keep their existing message instead of inventing one."""
    assert describe_launch_block(_oserror(2), target="the MTGO bridge") is None


def test_every_code_has_a_sentence() -> None:
    """A code added to the table with no matching sentence would raise KeyError
    inside a failure path -- the worst possible place for it."""
    for code in BLOCKED_WINERRORS:
        assert describe_launch_block(_oserror(code), target="it") is not None
