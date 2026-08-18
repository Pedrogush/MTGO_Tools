"""Behaviour of the styling layer, and the backwards compatibility it promises.

``widgets/stylize.py`` is applied at ~76 call sites across 10 modules. Phase 0
rewrites it, so these tests pin the two things that matter: the original call
signatures still produce the original rendering, and the new variants actually
differ from it.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from utils.constants import theme as T

wx = pytest.importorskip("wx")

from widgets import stylize  # noqa: E402
from widgets.checkbox import DarkCheckBox  # noqa: E402


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    instance = wx.App.Get() or wx.App()
    yield instance


@pytest.fixture
def frame(app: object) -> Iterator[object]:
    window = wx.Frame(None)
    yield window
    window.Destroy()


def _rgb(colour: object) -> tuple[int, int, int]:
    return (colour.Red(), colour.Green(), colour.Blue())


# --- stylize_label ---------------------------------------------------------
def test_legacy_label_is_primary_on_base_and_bold(frame: object) -> None:
    label = wx.StaticText(frame, label="x")
    stylize.stylize_label(label)
    assert _rgb(label.GetForegroundColour()) == T.TEXT_PRIMARY
    assert _rgb(label.GetBackgroundColour()) == T.SURFACE_BASE
    assert label.GetFont().GetWeight() == wx.FONTWEIGHT_BOLD


def test_legacy_subtle_label_is_secondary_on_panel_and_not_bold(frame: object) -> None:
    label = wx.StaticText(frame, label="x")
    stylize.stylize_label(label, True)  # positional, as 4 call sites do
    assert _rgb(label.GetForegroundColour()) == T.TEXT_SECONDARY
    assert _rgb(label.GetBackgroundColour()) == T.SURFACE_PANEL
    assert label.GetFont().GetWeight() != wx.FONTWEIGHT_BOLD


def test_body_level_is_not_bold(frame: object) -> None:
    """The blanket bold is exactly what `level` exists to retire."""
    label = wx.StaticText(frame, label="x")
    stylize.stylize_label(label, level="body")
    assert label.GetFont().GetWeight() != wx.FONTWEIGHT_BOLD


def test_heading_level_is_bold_and_at_least_1_2x_body(frame: object) -> None:
    body = wx.StaticText(frame, label="x")
    heading = wx.StaticText(frame, label="x")
    stylize.stylize_label(body, level="body")
    stylize.stylize_label(heading, level="heading")
    assert heading.GetFont().GetWeight() == wx.FONTWEIGHT_BOLD
    body_pt = body.GetFont().GetPointSize()
    heading_pt = heading.GetFont().GetPointSize()
    assert body_pt == T.BASE_FONT_POINT_SIZE
    assert heading_pt / body_pt >= 1.2


def test_type_levels_render_at_whole_points_off_the_declared_base(frame: object) -> None:
    """The rendered sizes must be the declared ladder, not the system font's."""
    rendered = {}
    for level in ("caption", "body", "heading", "title", "display"):
        label = wx.StaticText(frame, label="x")
        stylize.stylize_label(label, level=level)
        rendered[level] = label.GetFont().GetPointSize()
    assert rendered == T.type_ladder(T.BASE_FONT_POINT_SIZE)


def test_type_scale_ignores_the_widget_current_font_size(frame: object) -> None:
    """A label already at some odd size still lands on the ladder."""
    label = wx.StaticText(frame, label="x")
    font = label.GetFont()
    font.SetPointSize(24)
    label.SetFont(font)
    stylize.stylize_label(label, level="body")
    assert label.GetFont().GetPointSize() == T.BASE_FONT_POINT_SIZE


def test_theme_font_is_the_platform_face_at_the_declared_size(app: object) -> None:
    system = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    themed = stylize.theme_font()
    assert themed.GetPointSize() == T.BASE_FONT_POINT_SIZE
    assert themed.GetFaceName() == system.GetFaceName()


def test_apply_base_font_reaches_children_created_afterwards(app: object) -> None:
    """The inheritance behaviour apply_base_font depends on, pinned as a test.

    wxMSW copies the parent's font into a child at construction time only, so the
    call has to precede child creation. If a wx upgrade ever changes that, this
    fails rather than the app silently rendering at two sizes.
    """
    window = wx.Frame(None)
    try:
        stylize.apply_base_font(window)
        panel = wx.Panel(window)
        for child in (
            wx.StaticText(panel, label="x"),
            wx.Button(panel, label="x"),
            wx.TextCtrl(panel),
            wx.Choice(panel, choices=["a"]),
        ):
            assert child.GetFont().GetPointSize() == T.BASE_FONT_POINT_SIZE
    finally:
        window.Destroy()


def test_apply_base_font_does_not_reach_a_child_top_level_window(app: object) -> None:
    """Why every frame and dialog needs its own call, pinned as a test."""
    parent = wx.Frame(None)
    try:
        stylize.apply_base_font(parent)
        child_frame = wx.Frame(parent)
        assert child_frame.GetFont().GetPointSize() == stylize.system_point_size()
        assert child_frame.GetFont().GetPointSize() != T.BASE_FONT_POINT_SIZE
    finally:
        parent.Destroy()


def test_label_tone_override(frame: object) -> None:
    label = wx.StaticText(frame, label="x")
    stylize.stylize_label(label, tone="disabled", surface="alt")
    assert _rgb(label.GetForegroundColour()) == T.TEXT_DISABLED
    assert _rgb(label.GetBackgroundColour()) == T.SURFACE_ALT


def test_placeholder_label_uses_the_placeholder_token(frame: object) -> None:
    label = wx.StaticText(frame, label="x")
    stylize.stylize_placeholder_label(label)
    assert _rgb(label.GetForegroundColour()) == T.TEXT_PLACEHOLDER


# --- stylize_button --------------------------------------------------------
def test_default_button_is_unchanged_from_before_the_rewrite(frame: object) -> None:
    button = wx.Button(frame, label="x")
    stylize.stylize_button(button)
    assert _rgb(button.GetBackgroundColour()) == T.ACCENT_PRIMARY
    assert _rgb(button.GetForegroundColour()) == T.ACCENT_ON_PRIMARY
    assert button.GetFont().GetWeight() == wx.FONTWEIGHT_BOLD


@pytest.mark.parametrize("kind", ["secondary", "ghost", "danger", "success", "toggle"])
def test_non_primary_kinds_drop_the_accent_fill_and_the_bold(frame: object, kind: str) -> None:
    button = wx.Button(frame, label="x")
    stylize.stylize_button(button, kind=kind)
    assert _rgb(button.GetBackgroundColour()) != T.ACCENT_PRIMARY
    assert button.GetFont().GetWeight() != wx.FONTWEIGHT_BOLD


@pytest.mark.parametrize("kind", ["primary", "secondary", "ghost", "danger", "success", "toggle"])
def test_every_kind_strips_the_native_frame(frame: object, kind: str) -> None:
    """wxMSW's 2px light-grey button frame is unreachable; only removal is."""
    button = wx.Button(frame, label="x")
    assert not button.GetWindowStyleFlag() & wx.BORDER_NONE
    stylize.stylize_button(button, kind=kind)
    assert button.GetWindowStyleFlag() & wx.BORDER_NONE


def test_stripping_the_frame_is_idempotent(frame: object) -> None:
    """The view toggles are re-stylized on every switch; this must not churn."""
    button = wx.Button(frame, label="x", style=wx.BORDER_NONE)
    before = button.GetWindowStyleFlag()
    stylize.strip_native_button_frame(button)
    assert button.GetWindowStyleFlag() == before


def test_selected_toggle_is_the_selection_token(frame: object) -> None:
    button = wx.Button(frame, label="Grid")
    stylize.stylize_button(button, kind="toggle", selected=True, surface="panel")
    assert _rgb(button.GetBackgroundColour()) == T.SELECTION_FILL_ON_PANEL
    assert _rgb(button.GetForegroundColour()) == T.SELECTION_TEXT
    assert _rgb(button.GetBackgroundColour()) != T.ACCENT_PRIMARY


def test_a_ghost_chip_steps_up_so_it_does_not_vanish_into_its_surface(frame: object) -> None:
    """SURFACE_ALT is 1.32:1 on the base surface and 1.10:1 on a panel."""
    on_base = wx.Button(frame, label="Match History")
    on_panel = wx.Button(frame, label="Grid")
    stylize.stylize_button(on_base, kind="ghost")
    stylize.stylize_button(on_panel, kind="ghost", surface="panel")
    assert _rgb(on_base.GetBackgroundColour()) == T.SURFACE_ALT
    assert _rgb(on_panel.GetBackgroundColour()) == T.SURFACE_RAISED
    for button, surface in ((on_base, T.SURFACE_BASE), (on_panel, T.SURFACE_PANEL)):
        fill = _rgb(button.GetBackgroundColour())
        assert T.contrast_ratio(fill, surface) >= stylize._MIN_CHIP_CONTRAST


def test_a_toggle_can_be_deselected_again(frame: object) -> None:
    """Bold has to come back off, or a toggle stays bold forever after one click."""
    button = wx.Button(frame, label="Grid")
    stylize.stylize_button(button, kind="toggle", selected=True)
    assert button.GetFont().GetWeight() == wx.FONTWEIGHT_BOLD
    stylize.stylize_button(button, kind="toggle", selected=False)
    assert button.GetFont().GetWeight() == wx.FONTWEIGHT_NORMAL
    assert _rgb(button.GetBackgroundColour()) == T.SURFACE_ALT


def test_a_button_disabled_before_styling_is_painted_disabled(frame: object) -> None:
    """Half the app's Disable() calls happen before stylize_button, half after."""
    button = wx.Button(frame, label="Save Deck")
    button.Disable()
    stylize.stylize_button(button, kind="primary")
    assert _rgb(button.GetBackgroundColour()) == T.DISABLED_FILL


def test_a_button_disabled_after_styling_repaints_on_idle(frame: object) -> None:
    """C-b: wxMSW greys the label and leaves the fill saturated on its own."""
    button = wx.Button(frame, label="Save Deck")
    stylize.stylize_button(button, kind="primary")
    assert _rgb(button.GetBackgroundColour()) == T.ACCENT_PRIMARY
    button.Disable()
    button.ProcessEvent(wx.UpdateUIEvent(button.GetId()))
    assert _rgb(button.GetBackgroundColour()) == T.DISABLED_FILL
    button.Enable()
    button.ProcessEvent(wx.UpdateUIEvent(button.GetId()))
    assert _rgb(button.GetBackgroundColour()) == T.ACCENT_PRIMARY


def test_re_enabling_restores_the_kind_it_was_given(frame: object) -> None:
    button = wx.Button(frame, label="Flex Slots")
    stylize.stylize_button(button, kind="success")
    button.Disable()
    button.ProcessEvent(wx.UpdateUIEvent(button.GetId()))
    button.Enable()
    button.ProcessEvent(wx.UpdateUIEvent(button.GetId()))
    assert _rgb(button.GetBackgroundColour()) == T.SUCCESS_FILL


def test_disabled_button_loses_chroma(frame: object) -> None:
    button = wx.Button(frame, label="x")
    stylize.stylize_button(button, kind="primary", enabled=False)
    red, green, blue = _rgb(button.GetBackgroundColour())
    assert (red, green, blue) == T.DISABLED_FILL
    assert max(red, green, blue) - min(red, green, blue) < 30  # near-neutral


def test_unknown_button_kind_is_rejected(frame: object) -> None:
    button = wx.Button(frame, label="x")
    with pytest.raises(ValueError, match="unknown button kind"):
        stylize.stylize_button(button, kind="shouty")


# --- stylize_textctrl / stylize_choice -------------------------------------
def test_textctrl_is_themed_and_takes_a_placeholder(frame: object) -> None:
    ctrl = wx.TextCtrl(frame)
    stylize.stylize_textctrl(ctrl, placeholder="Search")
    assert _rgb(ctrl.GetBackgroundColour()) == T.SURFACE_ALT
    assert _rgb(ctrl.GetForegroundColour()) == T.TEXT_PRIMARY
    assert ctrl.GetHint() == "Search"


def test_multiline_textctrl_still_bumps_the_point_size(frame: object) -> None:
    plain = wx.TextCtrl(frame)
    multi = wx.TextCtrl(frame, style=wx.TE_MULTILINE)
    stylize.stylize_textctrl(plain)
    stylize.stylize_textctrl(multi, multiline=True)
    assert multi.GetFont().GetPointSize() == plain.GetFont().GetPointSize() + 1


def test_choice_is_themed_dark(frame: object) -> None:
    """Phase 1 flipped CHOICE_USES_NATIVE_THEME; dropdowns are dark now."""
    assert stylize.CHOICE_USES_NATIVE_THEME is False
    choice = wx.Choice(frame, choices=["a"])
    stylize.stylize_choice(choice)
    assert _rgb(choice.GetBackgroundColour()) == T.SURFACE_ALT
    assert _rgb(choice.GetForegroundColour()) == T.TEXT_PRIMARY


def test_choice_native_path_is_still_reachable(frame: object, monkeypatch: object) -> None:
    """The pre-phase-1 rendering stays one flag away, so the change is reversible."""
    monkeypatch.setattr(stylize, "CHOICE_USES_NATIVE_THEME", True)
    choice = wx.Choice(frame, choices=["a"])
    stylize.stylize_choice(choice)
    assert _rgb(choice.GetForegroundColour()) == (0, 0, 0)


def test_combobox_is_themed(frame: object) -> None:
    """Same Win32 control as wx.Choice, same constraints, its own entry point."""
    ctrl = wx.ComboBox(frame, choices=["a"], style=wx.CB_READONLY)
    stylize.stylize_combobox(ctrl)
    assert _rgb(ctrl.GetBackgroundColour()) == T.SURFACE_ALT
    assert _rgb(ctrl.GetForegroundColour()) == T.TEXT_PRIMARY


def test_checkbox_is_themed(frame: object) -> None:
    ctrl = DarkCheckBox(frame, label="Exact symbols")
    stylize.stylize_checkbox(ctrl, surface="panel")
    assert _rgb(ctrl.GetBackgroundColour()) == T.SURFACE_PANEL
    assert _rgb(ctrl.GetForegroundColour()) == T.TEXT_PRIMARY


def test_checkbox_accepts_a_tone(frame: object) -> None:
    ctrl = DarkCheckBox(frame, label="Auto-save art")
    stylize.stylize_checkbox(ctrl, surface="panel", tone="secondary")
    assert _rgb(ctrl.GetForegroundColour()) == T.TEXT_SECONDARY


def test_a_native_checkbox_still_gets_the_partial_fix(frame: object) -> None:
    """Not a call site any more, but the entry point must not blow up on one."""
    ctrl = wx.CheckBox(frame, label="Exact symbols")
    stylize.stylize_checkbox(ctrl, surface="panel")
    assert _rgb(ctrl.GetBackgroundColour()) == T.SURFACE_PANEL


def test_spinctrl_is_themed(frame: object) -> None:
    ctrl = wx.SpinCtrl(frame, min=0, max=10, initial=1)
    stylize.stylize_spinctrl(ctrl)
    assert _rgb(ctrl.GetBackgroundColour()) == T.SURFACE_ALT
    assert _rgb(ctrl.GetForegroundColour()) == T.TEXT_PRIMARY


def test_list_ctrl_rows_are_themed(frame: object) -> None:
    ctrl = wx.ListCtrl(frame, style=wx.LC_REPORT)
    ctrl.InsertColumn(0, "Card")
    stylize.stylize_list_ctrl(ctrl, surface="panel")
    assert _rgb(ctrl.GetBackgroundColour()) == T.SURFACE_PANEL
    assert _rgb(ctrl.GetForegroundColour()) == T.TEXT_PRIMARY


def test_disable_native_theme_is_safe_to_call(frame: object) -> None:
    """It must never raise: every stylize entry point calls it unconditionally."""
    choice = wx.Choice(frame, choices=["a"])
    assert isinstance(stylize.disable_native_theme(choice), bool)
