"""Collapsible advanced filter panel (type line, oracle text, mana value, color identity, format)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    DARK_ALT,
    DARK_PANEL,
    FORMAT_OPTIONS,
    LIGHT_TEXT,
    PADDING_MD,
    PADDING_SM,
    PADDING_XS,
)
from utils.stylize import stylize_button, stylize_choice, stylize_label, stylize_textctrl
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl

if TYPE_CHECKING:
    from utils.mana_icon_factory import ManaIconFactory


class AdvancedFiltersBuilderMixin:
    """Builds the toggle button and the collapsible advanced filters panel.

    Kept as a mixin (no ``__init__``) so :class:`DeckBuilderPanel` remains the
    single source of truth for instance-state initialization.
    """

    mana_icons: ManaIconFactory
    inputs: dict[str, wx.TextCtrl]
    mv_comparator: wx.Choice | None
    mv_value: wx.TextCtrl | None
    format_choice: wx.Choice | None
    color_checks: dict[str, wx.ToggleButton]
    color_mode_choice: wx.Choice | None
    text_mode_choice: wx.Choice | None
    _adv_panel: wx.Panel | None
    _adv_toggle_btn: wx.Button | None

    def _build_advanced_filters(self, parent_sizer: wx.Sizer) -> None:
        adv_toggle_btn = wx.Button(self, label=self._t("builder.btn.adv_filters_show"))
        stylize_button(adv_toggle_btn)
        adv_toggle_btn.Bind(wx.EVT_BUTTON, self._on_adv_toggle)
        parent_sizer.Add(adv_toggle_btn, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, PADDING_MD)
        self._adv_toggle_btn = adv_toggle_btn

        adv_panel = wx.Panel(self)
        adv_panel.SetBackgroundColour(DARK_PANEL)
        adv_sizer = wx.BoxSizer(wx.VERTICAL)
        adv_panel.SetSizer(adv_sizer)
        adv_panel.Hide()
        parent_sizer.Add(adv_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, PADDING_MD)
        self._adv_panel = adv_panel

        self._build_type_line_filter(adv_panel, adv_sizer)
        self._build_oracle_text_filter(adv_panel, adv_sizer)
        self._build_mana_value_filter(adv_panel, adv_sizer)
        self._build_color_and_format_filters(adv_panel, adv_sizer)

    def _build_type_line_filter(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        lbl = wx.StaticText(pwin, label=self._t("builder.field.type_line"))
        stylize_label(lbl, True)
        adv_sizer.Add(lbl, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.TOP, PADDING_MD)
        type_ctrl = wx.TextCtrl(pwin)
        stylize_textctrl(type_ctrl)
        type_ctrl.SetHint(self._t("builder.hint.type_line"))
        type_ctrl.SetToolTip("Filter cards by type line (e.g. Creature, Instant)")
        type_ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
        self.inputs["type"] = type_ctrl
        adv_sizer.Add(type_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

    def _build_oracle_text_filter(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        lbl = wx.StaticText(pwin, label=self._t("builder.field.oracle_text"))
        stylize_label(lbl, True)
        adv_sizer.Add(lbl, 0, wx.ALIGN_CENTER_HORIZONTAL, PADDING_MD)
        text_ctrl = ManaSymbolRichCtrl(
            pwin,
            self.mana_icons,
            readonly=False,
            multiline=False,
            ctrl_m_mana_mode=True,
        )
        text_ctrl.SetHint(self._t("builder.hint.oracle_text"))
        text_ctrl.SetToolTip(
            "Filter cards by oracle text\n"
            "Ctrl+M toggles mana symbol input mode:\n"
            "  Single key for basic symbols (W, U, B, R, G…)\n"
            "  Hold two keys at once for hybrids (W+U → {W/U}, 2+W → {2/W})\n"
            "  Press Ctrl+M again to return to normal typing"
        )
        text_ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
        self.inputs["text"] = text_ctrl
        text_row = wx.BoxSizer(wx.HORIZONTAL)
        text_row.Add(text_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)
        text_mode_choice = wx.Choice(pwin, choices=["=", "≈"])
        text_mode_choice.SetSelection(0)
        stylize_choice(text_mode_choice)
        text_mode_choice.SetToolTip("= matches all words; ≈ matches any word")
        self.text_mode_choice = text_mode_choice
        text_mode_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        text_row.Add(text_mode_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        adv_sizer.Add(text_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

    def _build_mana_value_filter(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        mv_label = wx.StaticText(pwin, label=self._t("builder.field.mana_value"))
        stylize_label(mv_label, True)
        adv_sizer.Add(mv_label, 0, wx.ALIGN_CENTER_HORIZONTAL, PADDING_MD)
        mv_row = wx.BoxSizer(wx.HORIZONTAL)
        mv_value = wx.TextCtrl(pwin)
        stylize_textctrl(mv_value)
        mv_value.SetHint(self._t("builder.hint.mana_value"))
        mv_value.SetToolTip("Enter a mana value (converted mana cost) to filter by")
        self.mv_value = mv_value
        mv_value.Bind(wx.EVT_TEXT, self._on_filters_changed)
        mv_row.Add(mv_value, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)
        mv_choice = wx.Choice(pwin, choices=["-", "<", "≤", "=", "≥", ">"])
        mv_choice.SetSelection(0)
        stylize_choice(mv_choice)
        mv_choice.SetToolTip("Comparison operator for the mana value filter")
        self.mv_comparator = mv_choice
        mv_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        mv_row.Add(mv_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        adv_sizer.Add(mv_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

    def _build_color_and_format_filters(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        # Color Identity Filter + Format (side by side)
        color_format_row = wx.BoxSizer(wx.HORIZONTAL)

        # Left: color identity label + controls
        color_col = wx.BoxSizer(wx.VERTICAL)
        color_label = wx.StaticText(pwin, label=self._t("builder.filter.color_identity"))
        stylize_label(color_label, True)
        color_col.Add(color_label, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, PADDING_XS)
        color_controls = wx.BoxSizer(wx.HORIZONTAL)
        color_mode = wx.Choice(pwin, choices=["-", "≥", "=", "≠"])
        color_mode.SetSelection(0)
        stylize_choice(color_mode)
        color_mode.SetToolTip("≥ includes, = exactly, ≠ excludes the selected colors")
        self.color_mode_choice = color_mode
        color_mode.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        color_controls.Add(color_mode, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)
        _color_names = {
            "W": "White",
            "U": "Blue",
            "B": "Black",
            "R": "Red",
            "G": "Green",
            "C": "Colorless",
        }
        _FILTER_ICON_SIZE = 32
        for code in ["W", "U", "B", "R", "G", "C"]:
            bmp: wx.Bitmap | None = None
            try:
                bmp = self.mana_icons.bitmap_for_symbol_hires(code)
            except Exception:
                bmp = None
            if bmp and bmp.IsOk():
                scaled = wx.Bitmap(
                    bmp.ConvertToImage().Scale(
                        _FILTER_ICON_SIZE, _FILTER_ICON_SIZE, wx.IMAGE_QUALITY_HIGH
                    )
                )
                grey_bmp = wx.Bitmap(scaled.ConvertToImage().ConvertToGreyscale())
                btn_size = (_FILTER_ICON_SIZE + 10, _FILTER_ICON_SIZE + 10)
                btn: wx.ToggleButton = wx.BitmapToggleButton(
                    pwin, wx.ID_ANY, grey_bmp, size=btn_size
                )
                btn.SetBitmapPressed(scaled)
            else:
                btn = wx.ToggleButton(pwin, label=code, size=(34, 34))
                btn.SetForegroundColour(LIGHT_TEXT)
            btn.SetBackgroundColour(DARK_ALT)
            btn.SetToolTip(f"Toggle {_color_names.get(code, code)} color filter")
            btn.Bind(wx.EVT_TOGGLEBUTTON, self._on_filters_changed)
            _btn_ref = btn
            btn.Bind(
                wx.EVT_ENTER_WINDOW,
                lambda evt, b=_btn_ref: (
                    b.SetBackgroundColour((60, 68, 80)),
                    b.Refresh(),
                    evt.Skip(),
                ),
            )
            btn.Bind(
                wx.EVT_LEAVE_WINDOW,
                lambda evt, b=_btn_ref: (b.SetBackgroundColour(DARK_ALT), b.Refresh(), evt.Skip()),
            )
            color_controls.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_XS)
            self.color_checks[code] = btn
        color_col.Add(color_controls, 0)
        color_format_row.Add(color_col, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_MD)

        # Right: format label + choice
        format_col = wx.BoxSizer(wx.VERTICAL)
        format_label = wx.StaticText(pwin, label=self._t("builder.filter.format"))
        stylize_label(format_label, True)
        format_col.Add(format_label, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, PADDING_XS)
        format_choice = wx.Choice(
            pwin, choices=[self._t("builder.format.any")] + list(FORMAT_OPTIONS)
        )
        format_choice.SetSelection(0)
        stylize_choice(format_choice)
        format_choice.SetToolTip("Filter results to cards legal in the selected format")
        self.format_choice = format_choice
        format_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        format_col.Add(format_choice, 0, wx.ALIGN_CENTER_HORIZONTAL)
        color_format_row.Add(format_col, 0, wx.ALIGN_CENTER_VERTICAL)

        adv_sizer.Add(color_format_row, 0, wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM, PADDING_SM)
