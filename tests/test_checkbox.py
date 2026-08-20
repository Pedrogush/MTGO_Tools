"""Behaviour of the own-drawn checkbox that replaced ``wx.CheckBox``.

The point of these is compatibility: ten call sites were migrated without any of
them changing how they read, write or listen to the control, so the contract they
rely on is what is pinned here. See ``widgets/checkbox.py`` for why the native
control could not be themed and why ``wx.lib.checkbox.GenCheckBox`` is not a way
out either.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from utils.constants import theme as T

wx = pytest.importorskip("wx")

from widgets.checkbox import DarkCheckBox  # noqa: E402


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    yield wx.App.Get() or wx.App()


@pytest.fixture
def frame(app: object) -> Iterator[object]:
    window = wx.Frame(None)
    yield window
    window.Destroy()


def _rgb(colour: object) -> tuple[int, int, int]:
    return (colour.Red(), colour.Green(), colour.Blue())


# --- wx.CheckBox-compatible surface ----------------------------------------
def test_starts_unchecked_and_reports_both_ways(frame: object) -> None:
    box = DarkCheckBox(frame, label="Exact symbols")
    assert box.GetValue() is False
    assert box.IsChecked() is False


def test_set_value_round_trips(frame: object) -> None:
    box = DarkCheckBox(frame, label="Exact symbols")
    box.SetValue(True)
    assert box.GetValue() is True
    box.SetValue(False)
    assert box.GetValue() is False


def test_set_value_does_not_fire_an_event(frame: object) -> None:
    """wx.CheckBox.SetValue is silent, and four call sites depend on that."""
    box = DarkCheckBox(frame, label="Use Radar Filter")
    fired: list[int] = []
    box.Bind(wx.EVT_CHECKBOX, lambda evt: fired.append(evt.GetInt()))
    box.SetValue(True)
    box.SetValue(False)
    assert fired == []


def test_clicking_toggles_and_fires_evt_checkbox(frame: object) -> None:
    box = DarkCheckBox(frame, label="Use Format Pool")
    fired: list[int] = []
    box.Bind(wx.EVT_CHECKBOX, lambda evt: fired.append(evt.GetInt()))
    box._on_left_down(wx.MouseEvent(wx.wxEVT_LEFT_DOWN))
    assert box.IsChecked() is True
    assert fired == [1]
    box._on_left_down(wx.MouseEvent(wx.wxEVT_LEFT_DOWN))
    assert box.IsChecked() is False
    assert fired == [1, 0]


def test_space_toggles_and_other_keys_do_not(frame: object) -> None:
    box = DarkCheckBox(frame, label="Auto-save art")
    space = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    space.SetKeyCode(wx.WXK_SPACE)
    box._on_key_down(space)
    assert box.IsChecked() is True

    tab = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    tab.SetKeyCode(wx.WXK_TAB)
    box._on_key_down(tab)
    assert box.IsChecked() is True


def test_a_disabled_box_ignores_clicks_and_keys(frame: object) -> None:
    box = DarkCheckBox(frame, label="Use Format Pool")
    box.Enable(False)
    box._on_left_down(wx.MouseEvent(wx.wxEVT_LEFT_DOWN))
    space = wx.KeyEvent(wx.wxEVT_KEY_DOWN)
    space.SetKeyCode(wx.WXK_SPACE)
    box._on_key_down(space)
    assert box.IsChecked() is False


def test_it_takes_keyboard_focus_while_enabled(frame: object) -> None:
    box = DarkCheckBox(frame, label="Exact symbols")
    assert box.AcceptsFocus() is True
    assert box.AcceptsFocusFromKeyboard() is True
    box.Enable(False)
    assert box.AcceptsFocusFromKeyboard() is False


# --- API the app deliberately does not have --------------------------------
def test_three_state_is_rejected_rather_than_silently_ignored(frame: object) -> None:
    with pytest.raises(ValueError, match="two-state only"):
        DarkCheckBox(frame, label="x", style=wx.CHK_3STATE)


# --- theming ---------------------------------------------------------------
def test_apply_theme_sets_surface_and_tone(frame: object) -> None:
    box = DarkCheckBox(frame, label="Auto-save art")
    box.apply_theme(surface="panel", tone="secondary")
    assert _rgb(box.GetBackgroundColour()) == T.SURFACE_PANEL
    assert _rgb(box.GetForegroundColour()) == T.TEXT_SECONDARY


def test_best_size_reserves_the_native_box_metric(frame: object) -> None:
    """Swapping the control in must not move the rows it sits in."""
    native = wx.CheckBox(frame, label="Exact symbols")
    dark = DarkCheckBox(frame, label="Exact symbols")
    dark.SetFont(native.GetFont())
    delta = abs(dark.GetBestSize().GetWidth() - native.GetBestSize().GetWidth())
    assert delta <= 8, "the drawn box + gap should match the native glyph + gap"


def test_it_paints_without_raising(frame: object) -> None:
    """Exercises every branch of the drawing code on a real DC."""
    box = DarkCheckBox(frame, label="Exact symbols")
    box.SetSize((160, 20))
    bitmap = wx.Bitmap(160, 20)
    dc = wx.MemoryDC(bitmap)
    for checked in (False, True):
        for enabled in (True, False):
            box.SetValue(checked)
            box.Enable(enabled)
            box._draw(dc)
    dc.SelectObject(wx.NullBitmap)
