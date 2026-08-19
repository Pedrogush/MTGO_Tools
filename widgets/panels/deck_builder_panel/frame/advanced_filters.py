"""Collapsible advanced filter panel (type line, oracle text, mana value, color identity, format)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    DARK_PANEL,
    FORMAT_OPTIONS,
    LIGHT_TEXT,
    SPACE_SM,
    SPACE_XS,
)
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl
from widgets.stylize import stylize_button, stylize_choice, stylize_label, stylize_textctrl

if TYPE_CHECKING:
    from widgets.panels.deck_builder_panel.protocol import DeckBuilderPanelProto

    _Base = DeckBuilderPanelProto
else:
    _Base = object


class AdvancedFiltersBuilderMixin(_Base):
    """Builds the toggle button and the collapsible advanced filters panel.

    Kept as a mixin (no ``__init__``) so :class:`DeckBuilderPanel` remains the
    single source of truth for instance-state initialization.
    """

    def _build_advanced_filters(self, parent_sizer: wx.Sizer) -> None:
        adv_toggle_btn = wx.Button(self, label=self._t("builder.btn.adv_filters_show"))
        stylize_button(adv_toggle_btn, kind="secondary")
        adv_toggle_btn.Bind(wx.EVT_BUTTON, self._on_adv_toggle)
        # A4: centred, with no horizontal border at all, between two left-aligned
        # rows. On the form gutter like everything else now.
        parent_sizer.Add(adv_toggle_btn, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)
        self._adv_toggle_btn = adv_toggle_btn

        adv_panel = wx.Panel(self)
        adv_panel.SetBackgroundColour(DARK_PANEL)
        adv_sizer = wx.BoxSizer(wx.VERTICAL)
        adv_panel.SetSizer(adv_sizer)
        adv_panel.Hide()
        # A1: this used to carry the form gutter itself (LEFT|RIGHT, SPACE_SM),
        # which meant its children could not use the same border value as the
        # basic rows without doubling it. The gutter moved onto the children, so
        # every label and field in this panel now sits on the *same* left edge as
        # "Card Name" and "Mana Cost" above it -- one label edge per column.
        parent_sizer.Add(adv_panel, 0, wx.EXPAND)
        self._adv_panel = adv_panel

        self._build_type_line_filter(adv_panel, adv_sizer)
        self._build_oracle_text_filter(adv_panel, adv_sizer)
        self._build_mana_value_filter(adv_panel, adv_sizer)
        self._build_color_and_format_filters(adv_panel, adv_sizer)

    def _build_type_line_filter(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        lbl = wx.StaticText(pwin, label=self._t("builder.field.type_line"))
        stylize_label(lbl, subtle=True, level="body")
        adv_sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)
        type_ctrl = wx.TextCtrl(pwin)
        stylize_textctrl(type_ctrl)
        type_ctrl.SetHint(self._t("builder.hint.type_line"))
        type_ctrl.SetToolTip("Filter cards by type line (e.g. Creature, Instant)")
        type_ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
        self.inputs["type"] = type_ctrl
        adv_sizer.Add(type_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, SPACE_SM)
        adv_sizer.AddSpacer(SPACE_XS)

    def _build_oracle_text_filter(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        lbl = wx.StaticText(pwin, label=self._t("builder.field.oracle_text"))
        stylize_label(lbl, subtle=True, level="body")
        adv_sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT, SPACE_SM)
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
        text_row.Add(text_ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)
        text_mode_choice = wx.Choice(pwin, choices=["=", "≈"])
        text_mode_choice.SetSelection(0)
        stylize_choice(text_mode_choice)
        text_mode_choice.SetToolTip("= matches all words; ≈ matches any word")
        self.text_mode_choice = text_mode_choice
        text_mode_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        text_row.Add(text_mode_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        adv_sizer.Add(text_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, SPACE_SM)
        adv_sizer.AddSpacer(SPACE_XS)

    def _build_mana_value_filter(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        mv_label = wx.StaticText(pwin, label=self._t("builder.field.mana_value"))
        stylize_label(mv_label, subtle=True, level="body")
        adv_sizer.Add(mv_label, 0, wx.LEFT | wx.RIGHT, SPACE_SM)
        mv_row = wx.BoxSizer(wx.HORIZONTAL)
        mv_value = wx.TextCtrl(pwin)
        stylize_textctrl(mv_value)
        mv_value.SetHint(self._t("builder.hint.mana_value"))
        mv_value.SetToolTip("Enter a mana value (converted mana cost) to filter by")
        self.mv_value = mv_value
        mv_value.Bind(wx.EVT_TEXT, self._on_filters_changed)
        mv_row.Add(mv_value, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)
        mv_choice = wx.Choice(pwin, choices=["-", "<", "≤", "=", "≥", ">"])
        mv_choice.SetSelection(0)
        stylize_choice(mv_choice)
        mv_choice.SetToolTip("Comparison operator for the mana value filter")
        self.mv_comparator = mv_choice
        mv_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        mv_row.Add(mv_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        adv_sizer.Add(mv_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, SPACE_SM)
        adv_sizer.AddSpacer(SPACE_XS)

    def _build_color_and_format_filters(self, pwin: wx.Panel, adv_sizer: wx.Sizer) -> None:
        # Color Identity Filter + Format (side by side)
        color_format_row = wx.BoxSizer(wx.HORIZONTAL)

        # Left: color identity label + controls
        color_col = wx.BoxSizer(wx.VERTICAL)
        color_label = wx.StaticText(pwin, label=self._t("builder.filter.color_identity"))
        stylize_label(color_label, subtle=True, level="body")
        color_col.Add(color_label, 0, wx.BOTTOM, SPACE_XS)
        color_controls = wx.BoxSizer(wx.HORIZONTAL)
        color_mode = wx.Choice(pwin, choices=["-", "≥", "=", "≠"])
        color_mode.SetSelection(0)
        stylize_choice(color_mode)
        color_mode.SetToolTip("≥ includes, = exactly, ≠ excludes the selected colors")
        self.color_mode_choice = color_mode
        color_mode.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        color_controls.Add(color_mode, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)
        _color_names = {
            "W": "White",
            "U": "Blue",
            "B": "Black",
            "R": "Red",
            "G": "Green",
            "C": "Colorless",
        }
        # G5: these used to be built from ``bitmap_for_symbol_hires`` rescaled to
        # a local 32px constant, giving 42x42 buttons beside the basic row's
        # 36x36 ones -- same glyphs, two sizes, for no reason. They now come off
        # exactly the same ``bitmap_for_symbol`` the mana keyboard uses, at the
        # factory's own size, so the two rows are the same size and the same
        # rasterisation.
        #
        # What deliberately does *not* change is the greyscale-until-selected
        # state. The plan reads "coloured here, greyscale there" as one defect;
        # measured against the controls, it is two different control *kinds* --
        # the basic row is push buttons that insert a symbol and have no off
        # state, this row is toggles, and desaturate-when-off is the state
        # encoding. Phase 2 established the alternative (accent tint + 2px
        # stroke) but also recorded that ``wx.ToggleButton``'s checked state
        # draws a ring in the *system* accent colour, which is a user setting we
        # cannot reach -- so a coloured-always toggle would have two competing
        # selection marks, one of them not ours.
        for code in ["W", "U", "B", "R", "G", "C"]:
            bmp: wx.Bitmap | None = None
            try:
                bmp = self.mana_icons.bitmap_for_symbol(code)
            except Exception:
                bmp = None
            if bmp and bmp.IsOk():
                grey_bmp = wx.Bitmap(bmp.ConvertToImage().ConvertToGreyscale())
                btn_size = (bmp.GetWidth() + 10, bmp.GetHeight() + 10)
                btn: wx.ToggleButton = wx.BitmapToggleButton(
                    pwin, wx.ID_ANY, grey_bmp, size=btn_size
                )
                btn.SetBitmapPressed(bmp)
            else:
                btn = wx.ToggleButton(pwin, label=code, size=(44, 28))
                btn.SetForegroundColour(LIGHT_TEXT)
            # Through the one button system rather than a hand-rolled fill and a
            # hand-rolled hover hex, exactly like create_mana_button.
            stylize_button(btn, kind="ghost")
            btn.SetToolTip(f"Toggle {_color_names.get(code, code)} color filter")
            btn.Bind(wx.EVT_TOGGLEBUTTON, self._on_filters_changed)
            color_controls.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)
            self.color_checks[code] = btn
        color_col.Add(color_controls, 0)
        color_format_row.Add(color_col, 0, wx.ALIGN_TOP | wx.RIGHT, SPACE_SM)

        # Right: format label + choice
        format_col = wx.BoxSizer(wx.VERTICAL)
        format_label = wx.StaticText(pwin, label=self._t("builder.filter.format"))
        stylize_label(format_label, subtle=True, level="body")
        format_col.Add(format_label, 0, wx.BOTTOM, SPACE_XS)
        format_choice = wx.Choice(
            pwin, choices=[self._t("builder.format.any")] + list(FORMAT_OPTIONS)
        )
        format_choice.SetSelection(0)
        stylize_choice(format_choice)
        format_choice.SetToolTip("Filter results to cards legal in the selected format")
        self.format_choice = format_choice
        format_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        format_col.Add(format_choice, 0, wx.EXPAND)
        color_format_row.Add(format_col, 0, wx.ALIGN_TOP)

        adv_sizer.Add(color_format_row, 0, wx.LEFT | wx.RIGHT, SPACE_SM)
        adv_sizer.AddSpacer(SPACE_XS)
