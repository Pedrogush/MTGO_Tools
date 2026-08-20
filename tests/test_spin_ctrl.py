"""Behaviour of the own-drawn spin control that replaced ``wx.SpinCtrl``.

The point of these is compatibility. Six call sites were migrated, all of them
driving real values -- deck size, copies in deck, cards drawn, target copies,
poll interval, repeat interval -- so what is pinned here is the contract they
rely on plus the behaviours a rewrite loses **silently**: the auto-repeat
acceleration and the fact that ``SetValue`` fires nothing while a user step
fires two events.

The native control's behaviour was measured with real Win32 input against the
running app before it was replaced (see ``widgets/spin_ctrl.py``); these tests
are the part of that measurement that can be re-run without a screen.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

wx = pytest.importorskip("wx")

from widgets.spin_ctrl import DarkSpinCtrl, repeat_step  # noqa: E402


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    yield wx.App.Get() or wx.App()


@pytest.fixture
def frame(app: object) -> Iterator[object]:
    window = wx.Frame(None)
    yield window
    window.Destroy()


def _spin(parent: object, **kwargs: object) -> DarkSpinCtrl:
    kwargs.setdefault("min", 1)
    kwargs.setdefault("max", 250)
    kwargs.setdefault("initial", 60)
    return DarkSpinCtrl(parent, **kwargs)


# --- wx.SpinCtrl-compatible surface ----------------------------------------
def test_reports_its_initial_value_and_range(frame: object) -> None:
    spin = _spin(frame)
    assert spin.GetValue() == 60
    assert (spin.GetMin(), spin.GetMax()) == (1, 250)


def test_initial_value_is_clamped_into_range(frame: object) -> None:
    assert _spin(frame, initial=9999).GetValue() == 250
    assert _spin(frame, initial=-5).GetValue() == 1


def test_set_value_round_trips_and_clamps(frame: object) -> None:
    spin = _spin(frame)
    spin.SetValue(7)
    assert spin.GetValue() == 7
    spin.SetValue(9999)
    assert spin.GetValue() == 250
    spin.SetValue(0)
    assert spin.GetValue() == 1


def test_set_value_accepts_a_string_like_wx_spinctrl(frame: object) -> None:
    spin = _spin(frame)
    spin.SetValue("42")
    assert spin.GetValue() == 42


def test_the_field_shows_the_value(frame: object) -> None:
    spin = _spin(frame)
    spin.SetValue(33)
    assert spin.ctrl.GetValue() == "33"


def test_set_range_reclamps_the_current_value(frame: object) -> None:
    spin = _spin(frame)
    spin.SetValue(200)
    spin.SetRange(1, 60)
    assert spin.GetValue() == 60


# --- events -----------------------------------------------------------------
def test_set_value_fires_nothing(frame: object) -> None:
    """``wx.SpinCtrl.SetValue`` is silent, and ``_apply_preset`` calls it twice."""
    spin = _spin(frame)
    fired: list[str] = []
    spin.Bind(wx.EVT_SPINCTRL, lambda evt: fired.append("spin"))
    spin.Bind(wx.EVT_TEXT, lambda evt: fired.append("text"))
    spin.SetValue(30)
    assert fired == []


def test_a_user_step_fires_spinctrl_and_text(frame: object) -> None:
    spin = _spin(frame)
    fired: list[tuple[str, int]] = []
    spin.Bind(wx.EVT_SPINCTRL, lambda evt: fired.append(("spin", evt.GetPosition())))
    spin.Bind(wx.EVT_TEXT, lambda evt: fired.append(("text", int(evt.GetString()))))
    spin.step(1)
    assert fired == [("spin", 61), ("text", 61)]


def test_a_step_that_changes_nothing_fires_nothing(frame: object) -> None:
    """At the top of the range the arrow is inert, as the native one is."""
    spin = _spin(frame, initial=250)
    fired: list[str] = []
    spin.Bind(wx.EVT_SPINCTRL, lambda evt: fired.append("spin"))
    spin.step(1)
    assert spin.GetValue() == 250
    assert fired == []


def test_stepping_clamps_rather_than_wrapping(frame: object) -> None:
    spin = _spin(frame, initial=2)
    spin.step(-1, 10)
    assert spin.GetValue() == 1


# --- auto-repeat ------------------------------------------------------------
def test_repeat_acceleration_matches_the_measured_native_table() -> None:
    """comctl32's default ``UDACCEL``, measured off the live control.

    A 6s hold on the native Deck Size arrow was polled through ``WM_GETTEXT``:
    step 1 until t=2.33s, then 5. This is the behaviour most likely to be lost
    without anyone noticing, because a screenshot cannot show it.
    """
    assert repeat_step(0.0) == 1
    assert repeat_step(1.99) == 1
    assert repeat_step(2.0) == 5
    assert repeat_step(4.99) == 5
    assert repeat_step(5.0) == 20
    assert repeat_step(30.0) == 20


# --- geometry ---------------------------------------------------------------
def test_best_width_does_not_inherit_the_text_ctrl_floor(frame: object) -> None:
    """Phase 8 measured a **110px** floor on ``wx.TextCtrl.GetBestSize()``.

    ``InputFrame`` hands that straight back, and inheriting it here would widen
    the timer alert's options grid in a window that already wants more width
    than it has.
    """
    assert _spin(frame, min=0, max=99).GetBestSize().width < 110


def test_it_is_as_tall_as_a_native_spin_control(frame: object) -> None:
    """25px on this toolchain, i.e. no row in either window moves.

    The field is built *without* ``wx.BORDER_NONE`` precisely for this: a
    borderless ``wx.TextCtrl`` reports a best height of 17.
    """
    native = wx.SpinCtrl(frame, min=1, max=250, initial=60)
    try:
        assert _spin(frame).GetBestSize().height == native.GetBestSize().height
    finally:
        native.Destroy()


def test_the_arrows_are_never_a_tab_stop(frame: object) -> None:
    """The native arrows are not one either -- verified live with real Tab keys."""
    spin = _spin(frame)
    assert spin._arrows.AcceptsFocus() is False
    assert spin._arrows.AcceptsFocusFromKeyboard() is False


# --- refusals ---------------------------------------------------------------
def test_wrapping_is_refused_rather_than_silently_ignored(frame: object) -> None:
    with pytest.raises(ValueError, match="does not wrap"):
        DarkSpinCtrl(frame, min=1, max=10, initial=1, style=wx.SP_WRAP)


def test_an_inverted_range_is_refused(frame: object) -> None:
    with pytest.raises(ValueError, match="above max"):
        DarkSpinCtrl(frame, min=10, max=1)
