from __future__ import annotations

import importlib
import importlib.util
import sys
from unittest.mock import MagicMock, patch

import pytest


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


_WX_AVAILABLE = importlib.util.find_spec("wx") is not None
_requires_wx = pytest.mark.skipif(
    not _WX_AVAILABLE or sys.platform != "win32",
    reason="AppFrame tutorial-skip checks require wxPython (Windows-only)",
)


def _call_restore_session_state(is_automation: bool, tutorial_shown: bool):
    """Invoke AppFrame._restore_session_state unbound with mocked collaborators."""
    from widgets import app_frame as app_frame_module

    frame = MagicMock()
    frame.controller.zone_cards = {"main": [], "side": [], "out": []}
    frame.controller.session_manager.restore_session_state.return_value = {
        "left_mode": "research",
    }
    frame.controller.session_manager.is_tutorial_shown.return_value = tutorial_shown
    frame.controller.card_repo.is_card_data_ready.return_value = True

    with (
        patch.object(app_frame_module, "is_automation_enabled", return_value=is_automation),
        patch.object(app_frame_module, "wx") as wx_mock,
    ):
        app_frame_module.AppFrame._restore_session_state(frame)
        return wx_mock, frame


@_requires_wx
def test_restore_session_state_schedules_tutorial_when_not_shown_and_not_automation():
    wx_mock, frame = _call_restore_session_state(is_automation=False, tutorial_shown=False)
    wx_mock.CallAfter.assert_called_once_with(frame._open_tutorial)


@_requires_wx
def test_restore_session_state_skips_tutorial_under_automation():
    wx_mock, _frame = _call_restore_session_state(is_automation=True, tutorial_shown=False)
    wx_mock.CallAfter.assert_not_called()


@_requires_wx
def test_restore_session_state_skips_tutorial_when_already_shown():
    wx_mock, _frame = _call_restore_session_state(is_automation=False, tutorial_shown=True)
    wx_mock.CallAfter.assert_not_called()
