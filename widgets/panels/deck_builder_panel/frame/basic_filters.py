"""Basic filter row construction (back button, info, name, mana cost, exact match, mana keyboard)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    BUILDER_MANA_ALL_BTN_SIZE,
    SPACE_SM,
    SPACE_XS,
)
from widgets.buttons.mana_button import create_mana_button
from widgets.checkbox import DarkCheckBox
from widgets.input_frame import create_text_input
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl
from widgets.stylize import stylize_button, stylize_checkbox, stylize_label

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
        # F2: a full-width saturated bar reads as a section header, not a switch.
        stylize_button(back_btn, kind="secondary")
        back_btn.SetToolTip(self._t("builder.back_button.tooltip"))
        back_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_back_clicked())
        parent_sizer.Add(back_btn, 0, wx.EXPAND | wx.ALL, SPACE_SM)

        info = wx.StaticText(self, label=self._t("builder.info"))
        stylize_label(info, subtle=True, level="body")
        parent_sizer.Add(info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)

    def _build_basic_filters(self, parent_sizer: wx.Sizer) -> None:
        # --- Card Name (always visible) ---
        lbl = wx.StaticText(self, label=self._t("builder.field.card_name"))
        stylize_label(lbl, subtle=True, level="body")
        parent_sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT, SPACE_SM)
        name_field = create_text_input(self)
        name_ctrl = name_field.ctrl
        name_ctrl.SetHint(self._t("builder.hint.card_name"))
        name_ctrl.SetToolTip("Filter cards by name")
        name_ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
        self.inputs["name"] = name_ctrl
        # A1: LEFT/RIGHT is the form gutter, so the field lines up with its
        # label; the row gap stays SPACE_XS via the spacer, because a sizer
        # item has a single border value for every side it is given.
        parent_sizer.Add(name_field, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, SPACE_SM)
        parent_sizer.AddSpacer(SPACE_XS)

        # --- Mana Cost (always visible) ---
        lbl = wx.StaticText(self, label=self._t("builder.field.mana_cost"))
        stylize_label(lbl, subtle=True, level="body")
        parent_sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT, SPACE_SM)
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
        # A1: LEFT/RIGHT is the form gutter, so the field lines up with its
        # label; the row gap stays SPACE_XS via the spacer, because a sizer
        # item has a single border value for every side it is given.
        parent_sizer.Add(mana_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, SPACE_SM)
        parent_sizer.AddSpacer(SPACE_XS)

        # Exact match checkbox.
        #
        # G3: a bare "Match" StaticText used to sit to the left of this checkbox.
        # The plan read it as labelling the *mana keyboard row below it*; it
        # actually read as a second label for a control that already carries one
        # ("Match" + "Exact symbols" for one checkbox). Either way it named
        # nothing the reader could point at, so the word moved into the
        # checkbox's own label and the orphan is gone.
        exact_cb = DarkCheckBox(self, label=self._t("builder.check.exact_symbols"))
        stylize_checkbox(exact_cb, surface="panel")
        exact_cb.SetToolTip("When checked, match the exact mana symbols (no extras allowed)")
        self.mana_exact_cb = exact_cb
        exact_cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
        parent_sizer.Add(exact_cb, 0, wx.LEFT | wx.RIGHT, SPACE_SM)
        parent_sizer.AddSpacer(SPACE_XS)

        # Mana symbol keyboard
        # A4: this row and the "+ Advanced Filters" button below it were the only
        # two centred rows in an otherwise left-aligned column -- three
        # consecutive rows, three alignments. Both are left-aligned now, on the
        # same form gutter as every label and field.
        keyboard_row = wx.BoxSizer(wx.HORIZONTAL)
        mana_btn_height = 0
        for token in ["W", "U", "B", "R", "G", "C", "X"]:
            btn = create_mana_button(self, token, self._append_mana_symbol, self.mana_icons)
            mana_btn_height = max(mana_btn_height, btn.GetSize().GetHeight())
            keyboard_row.Add(btn, 0, wx.ALL, SPACE_XS)
        # G4: "All" opens the rest of this same keyboard, so it gets the same face
        # and the same height as the seven buttons beside it. It keeps its own
        # width because it carries a word rather than a glyph. The height is taken
        # from a real mana button rather than hard-coded, since that one depends on
        # the loaded icon size.
        all_btn = wx.Button(self, label="All", size=BUILDER_MANA_ALL_BTN_SIZE)
        if mana_btn_height:
            all_btn.SetMinSize((BUILDER_MANA_ALL_BTN_SIZE[0], mana_btn_height))
        stylize_button(all_btn, kind="ghost")
        all_btn.SetToolTip("Open the full mana symbol keyboard")
        all_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._open_mana_keyboard())
        keyboard_row.Add(all_btn, 0, wx.ALL, SPACE_XS)
        keyboard_row.AddStretchSpacer(1)
        # The buttons carry their own SPACE_XS margin, so SPACE_XS here puts the
        # first glyph's left edge on the SPACE_SM form gutter.
        parent_sizer.Add(keyboard_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_XS)
