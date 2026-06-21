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
from utils.constants import DARK_ACCENT, DARK_ALT, LIGHT_TEXT
from widgets.panels.card_table_panel.sorting import (
    PILE_SORT_COLOR,
    PILE_SORT_MV,
    PILE_SORT_TYPE,
)
from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from widgets.panels.card_table_panel.protocol import CardTablePanelProto

    _Base = CardTablePanelProto
else:
    _Base = object


class CardTablePanelToolbarMixin(_Base):
    """View-mode buttons, pile-sort menu, and printing dropdown for the panel."""

    def _column_label(self, col_id: str) -> str:
        return self._t(f"tabs.view.col.{col_id}")

    def _refresh_view_mode_buttons(self) -> None:
        for mode, btn in self._view_mode_buttons.items():
            active = mode == self.view_mode
            btn.SetBackgroundColour(wx.Colour(*(DARK_ACCENT if active else DARK_ALT)))
            btn.SetForegroundColour(wx.Colour(*LIGHT_TEXT))
            btn.Refresh()

    def _update_pile_sort_button_visibility(self) -> None:
        self.pile_sort_button.Show(self.view_mode == "pile")
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
