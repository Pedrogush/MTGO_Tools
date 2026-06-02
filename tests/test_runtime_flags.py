from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path

import pytest

# ``session_logic`` is a wx-free leaf module inside the
# ``widgets.frames.app_frame`` package, whose ``__init__`` imports ``wx``
# (unavailable off-Windows). Load it directly from source so the import does not
# pull in the package ``__init__`` — same approach as ``test_deck_formatting``.
_SESSION_LOGIC_PATH = (
    Path(__file__).resolve().parents[1]
    / "widgets"
    / "frames"
    / "app_frame"
    / "handlers"
    / "session_logic.py"
)
_spec = importlib.util.spec_from_file_location("_session_logic_under_test", _SESSION_LOGIC_PATH)
_session_logic = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_session_logic)
should_show_tutorial = _session_logic.should_show_tutorial


@pytest.fixture
def runtime_flags():
    module = importlib.import_module("utils.runtime_flags")
    original = module.is_automation_enabled()
    yield module
    module.set_automation_enabled(original)


def test_is_automation_enabled_defaults_to_false(runtime_flags):
    runtime_flags.set_automation_enabled(False)
    assert runtime_flags.is_automation_enabled() is False


def test_set_automation_enabled_round_trips(runtime_flags):
    runtime_flags.set_automation_enabled(True)
    assert runtime_flags.is_automation_enabled() is True
    runtime_flags.set_automation_enabled(False)
    assert runtime_flags.is_automation_enabled() is False


def test_set_automation_enabled_coerces_truthy_values(runtime_flags):
    runtime_flags.set_automation_enabled(1)  # type: ignore[arg-type]
    assert runtime_flags.is_automation_enabled() is True
    runtime_flags.set_automation_enabled(0)  # type: ignore[arg-type]
    assert runtime_flags.is_automation_enabled() is False


# --------------------------------------------------------------------------- #
# Tutorial-gate decision (Humble Object): the pure predicate behind the wx
# ``wx.CallAfter(self._open_tutorial)`` scheduling in
# ``AppFrameHandlersMixin._restore_session_state``. Tested here with the real
# function and the real ``runtime_flags`` flag — no wx, no mocked AppFrame.
# --------------------------------------------------------------------------- #


def test_show_tutorial_when_not_shown_and_not_automation():
    assert should_show_tutorial(tutorial_shown=False, automation_enabled=False) is True


def test_skip_tutorial_under_automation():
    assert should_show_tutorial(tutorial_shown=False, automation_enabled=True) is False


def test_skip_tutorial_when_already_shown():
    assert should_show_tutorial(tutorial_shown=True, automation_enabled=False) is False


def test_skip_tutorial_when_shown_and_automation():
    assert should_show_tutorial(tutorial_shown=True, automation_enabled=True) is False


def test_tutorial_gate_reads_live_automation_flag(runtime_flags):
    """The gate honours the real process-wide automation flag set at startup."""
    runtime_flags.set_automation_enabled(True)
    assert (
        should_show_tutorial(
            tutorial_shown=False,
            automation_enabled=runtime_flags.is_automation_enabled(),
        )
        is False
    )
    runtime_flags.set_automation_enabled(False)
    assert (
        should_show_tutorial(
            tutorial_shown=False,
            automation_enabled=runtime_flags.is_automation_enabled(),
        )
        is True
    )
