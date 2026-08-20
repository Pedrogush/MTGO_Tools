"""Toolbar / menu interaction mixin for the card table panel.

This is the actively-growing toolbar surface — the view-mode buttons, the
pile-sort menu, and the printing-selection dropdown (issue #792). Keeping it in
one mixin lets the printing-dropdown concern (which imports
``PRINTING_MODES`` / ``PRINTING_DATE_MODES``) live in a single place rather than
threaded through the construction core in ``frame.py``.

Kept as a mixin (no ``__init__``); :class:`CardTablePanel` owns all instance
state the methods here reach through ``self``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from services.deck_service.printing import DATE_MODES as PRINTING_DATE_MODES
from services.deck_service.printing import PRINTING_MODES
from utils.constants import (
    DECK_COUNT_LABEL_MIN_WIDTH,
    SPACE_SM,
    VIEW_TOGGLE_HEIGHT,
    VIEW_TOGGLE_PADDING_X,
)
from widgets.panels.card_table_panel.sorting import (
    PILE_SORT_COLOR,
    PILE_SORT_MV,
    PILE_SORT_TYPE,
)
from widgets.stylize import size_compact_button, stylize_button
from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from widgets.panels.card_table_panel.protocol import CardTablePanelProto

    _Base = CardTablePanelProto
else:
    _Base = object


#: Appended to a button that opens a menu rather than acting immediately (F3).
#: The two controls it marks -- the pile-sort key and the printing selector --
#: sat in the run of view-toggle chips looking exactly like them, which is what
#: made them read as a fourth and fifth view mode.
MENU_CARET = "\u25be"


class CardTablePanelToolbarMixin(_Base):
    """View-mode buttons, pile-sort menu, and printing dropdown for the panel."""

    def _on_panel_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        self._reflow_header()

    def _reflow_header(self) -> None:
        """Move the view controls to their own line when the header row is too narrow.

        The row's minimum is view-mode *and* locale dependent -- 310px in en-US
        grid view, 496 in pt-BR pile view -- and the deck workspace's own floor
        is 353. Sizing the workspace for the worst case would cost the window
        ~150px of minimum width for a toolbar that is only that wide in one view
        and one language, and leaving it alone means wxBoxSizer silently paints
        whichever control is last at whatever is left (phase 7 measured that at
        14px against a 59px minimum).

        Hysteresis is not needed: moving the controls down changes the panel's
        *height*, never its width, so the predicate this reads cannot flip as a
        result of acting on it. The early return on an unchanged state is what
        keeps the EVT_SIZE this triggers from recursing.
        """
        controls = getattr(self, "_header_controls", None)
        if controls is None:
            return
        needed = controls.CalcMin().GetWidth() + DECK_COUNT_LABEL_MIN_WIDTH + SPACE_SM + SPACE_SM
        wrapped = self.GetClientSize().GetWidth() < needed
        if wrapped == self._header_wrapped:
            return
        self._header_wrapped = wrapped
        if wrapped:
            self._header_top.Detach(controls)
            self._header_bottom.AddStretchSpacer(1)
            self._header_bottom.Add(controls, 0, wx.ALIGN_CENTER_VERTICAL)
        else:
            self._header_bottom.Detach(controls)
            self._header_bottom.Clear(False)
            self._header_top.Add(controls, 0, wx.ALIGN_CENTER_VERTICAL)
        self._header_stack.Layout()
        self.Layout()

    def _column_label(self, col_id: str) -> str:
        return self._t(f"tabs.view.col.{col_id}")

    def _refresh_view_mode_buttons(self) -> None:
        # C9/G1: the active view is a *selection*, so it wears the app's one
        # selection idiom rather than a saturated fill of its own. The old pairing
        # was also LIGHT_TEXT on ACCENT_PRIMARY, which measures 3.11:1 and failed
        # AA — nothing in the review or the plan had caught that.
        for mode, btn in self._view_mode_buttons.items():
            stylize_button(
                btn,
                kind="toggle",
                selected=mode == self.view_mode,
                surface="panel",
            )
            # F4: BU_EXACTFIT sized these to the text extent plus ~2px (30x18
            # measured). size_compact_button measures the bold face whatever the
            # current weight, so re-running it on every selection change is a
            # no-op for layout -- the chip keeps one width as selection moves.
            size_compact_button(btn, pad_x=VIEW_TOGGLE_PADDING_X, height=VIEW_TOGGLE_HEIGHT)
            btn.Refresh()

    def _pile_sort_label(self) -> str:
        """The pile-sort button's label: the grouping key it will change.

        F3 called this control "mystery meat"; it was labelled ``⋯``. F7 is the
        same defect one level down -- the grouping key (mana value / colour /
        type) was reachable only by opening this menu and reading which item was
        ticked. Naming the current key on the button states it without a click,
        and the per-pile headings (:mod:`widgets.panels.card_table_panel.pile_view`)
        state each bucket.
        """
        key = {
            PILE_SORT_MV: "mv",
            PILE_SORT_COLOR: "color",
            PILE_SORT_TYPE: "type",
        }.get(self.pile_sort, "mv")
        return f"{self._t(f'tabs.view.pile_sort.{key}')} {MENU_CARET}"

    def _refresh_pile_sort_button(self) -> None:
        self.pile_sort_button.SetLabel(self._pile_sort_label())
        size_compact_button(
            self.pile_sort_button, pad_x=VIEW_TOGGLE_PADDING_X, height=VIEW_TOGGLE_HEIGHT
        )

    def _update_pile_sort_button_visibility(self) -> None:
        self.pile_sort_button.Show(self.view_mode == "pile")
        # The divider marks the boundary of the toggle group; with nothing left
        # of it visible it would be a rule against the panel edge.
        self.header_divider.Show(self.view_mode == "pile" or self.printing_button is not None)
        relayout(self)

    def _on_view_button(self, mode: str) -> None:
        self.set_view_mode(mode)

    def _open_pile_sort_menu(self, _event: wx.CommandEvent) -> None:
        menu = wx.Menu()
        items = (
            (PILE_SORT_MV, self._t("tabs.view.pile_sort.mv")),
            (PILE_SORT_COLOR, self._t("tabs.view.pile_sort.color")),
            (PILE_SORT_TYPE, self._t("tabs.view.pile_sort.type")),
        )
        for sort_mode, label in items:
            item = menu.AppendCheckItem(wx.ID_ANY, label)
            item.Check(sort_mode == self.pile_sort)
            menu.Bind(wx.EVT_MENU, lambda _evt, m=sort_mode: self.set_pile_sort(m), item)
        self.PopupMenu(menu, self.pile_sort_button.GetPosition())
        menu.Destroy()

    def _open_printing_menu(self, _event: wx.CommandEvent) -> None:
        """Show the printing-selection menu and dispatch the chosen mode."""
        menu = wx.Menu()
        for mode in PRINTING_MODES:
            item = menu.Append(wx.ID_ANY, self._t(f"tabs.view.printing.{mode}"))
            menu.Bind(wx.EVT_MENU, lambda _evt, m=mode: self._on_printing_choice(m), item)
        anchor = self.printing_button or self
        self.PopupMenu(menu, anchor.GetPosition())
        menu.Destroy()

    def _on_printing_choice(self, mode: str) -> None:
        if self._on_printing_mode is None:
            return
        when: str | None = None
        if mode in PRINTING_DATE_MODES:
            dialog = wx.TextEntryDialog(
                self,
                self._t("tabs.view.printing.date_prompt"),
                self._t("tabs.view.printing.date_title"),
            )
            try:
                if dialog.ShowModal() != wx.ID_OK:
                    return
                when = dialog.GetValue().strip()
            finally:
                dialog.Destroy()
            if not when:
                return
        self._on_printing_mode(mode, when)
