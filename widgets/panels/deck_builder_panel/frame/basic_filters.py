"""Basic filter row construction (back button, info, name, mana cost, exact match, mana keyboard)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    BUILDER_MANA_ALL_BTN_SIZE,
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_MD,
    PADDING_SM,
    PADDING_XS,
)
from utils.stylize import stylize_button, stylize_label, stylize_textctrl
from widgets.buttons.mana_button import create_mana_button
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl

if TYPE_CHECKING:
    from widgets.panels.deck_builder_panel.protocol import DeckBuilderPanelProto

    _Base = DeckBuilderPanelProto
else:
    _Base = object


class BasicFiltersBuilderMixin(_Base):
    """Builds the back button, info label, and the always-visible filter rows.

    Kept as a mixin (no ``__init__``) so :class:`DeckBuilderPanel` remains the
    single source of truth for instance-state initialization.
    """

    def _build_header(self, parent_sizer: wx.Sizer) -> None:
        back_btn = wx.Button(self, label=self._t("builder.back_button"))
        stylize_button(back_btn)
        back_btn.SetToolTip(self._t("builder.back_button.tooltip"))
        back_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_back_clicked())
        parent_sizer.Add(back_btn, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        info = wx.StaticText(self, label=self._t("builder.info"))
        stylize_label(info, True)
        parent_sizer.Add(info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

    def _build_basic_filters(self, parent_sizer: wx.Sizer) -> None:
        # --- Card Name (always visible) ---
        lbl = wx.StaticText(self, label=self._t("builder.field.card_name"))
        stylize_label(lbl, True)
        parent_sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT, PADDING_MD)
        name_ctrl = wx.TextCtrl(self)
        stylize_textctrl(name_ctrl)
        name_ctrl.SetHint(self._t("builder.hint.card_name"))
        name_ctrl.SetToolTip("Filter cards by name")
        name_ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
        self.inputs["name"] = name_ctrl
        parent_sizer.Add(name_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

        # --- Mana Cost (always visible) ---
        lbl = wx.StaticText(self, label=self._t("builder.field.mana_cost"))
        stylize_label(lbl, True)
        parent_sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT, PADDING_MD)
        mana_ctrl = ManaSymbolRichCtrl(
            self,
            self.mana_icons,
            readonly=False,
            multiline=False,
            mana_key_input=True,
        )
        mana_ctrl.SetHint(self._t("builder.hint.mana_cost"))
        mana_ctrl.SetToolTip(
            "Type single letters to enter mana symbols (W, U, B, R, G, C, X, 0-9)\n"
            "Hold two keys at once for hybrid symbols (W+U → {W/U}, 2+W → {2/W})\n"
            "Backspace removes the last symbol; Delete clears all"
        )
        mana_ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
        self.inputs["mana"] = mana_ctrl
        parent_sizer.Add(mana_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

        # Exact match checkbox
        match_row = wx.BoxSizer(wx.HORIZONTAL)
        match_label = wx.StaticText(self, label=self._t("builder.label.match"))
        stylize_label(match_label, True)
        match_row.Add(match_label, 0, wx.RIGHT, PADDING_MD)
        exact_cb = wx.CheckBox(self, label=self._t("builder.check.exact_symbols"))
        exact_cb.SetForegroundColour(LIGHT_TEXT)
        exact_cb.SetBackgroundColour(DARK_PANEL)
        exact_cb.SetToolTip("When checked, match the exact mana symbols (no extras allowed)")
        match_row.Add(exact_cb, 0)
        self.mana_exact_cb = exact_cb
        exact_cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
        match_row.AddStretchSpacer(1)
        parent_sizer.Add(match_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_XS)

        # Mana symbol keyboard
        keyboard_row = wx.BoxSizer(wx.HORIZONTAL)
        keyboard_row.AddStretchSpacer(1)
        for token in ["W", "U", "B", "R", "G", "C", "X"]:
            btn = create_mana_button(self, token, self._append_mana_symbol, self.mana_icons)
            keyboard_row.Add(btn, 0, wx.ALL, PADDING_XS)
        all_btn = wx.Button(self, label="All", size=BUILDER_MANA_ALL_BTN_SIZE)
        stylize_button(all_btn)
        all_btn.SetToolTip("Open the full mana symbol keyboard")
        all_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._open_mana_keyboard())
        keyboard_row.Add(all_btn, 0, wx.ALL, PADDING_XS)
        keyboard_row.AddStretchSpacer(1)
        parent_sizer.Add(
            keyboard_row,
            0,
            wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            PADDING_XS,
        )
