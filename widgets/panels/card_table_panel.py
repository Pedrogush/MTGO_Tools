from collections.abc import Callable
from typing import Any

import wx
import wx.lib.scrolledpanel as scrolled

from utils.constants import DARK_PANEL, SUBDUED_TEXT
from utils.mana_icon_factory import ManaIconFactory
from widgets.panels.card_box_panel import CardBoxPanel


class CardTablePanel(wx.Panel):
    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        icon_factory: ManaIconFactory,
        get_metadata: Callable[[str], dict[str, Any] | None],
        owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]],
        on_delta: Callable[[str, str, int], None],
        on_remove: Callable[[str, str], None],
        on_add: Callable[[str], None],
        on_select: Callable[[str, dict[str, Any] | None], None],
        on_hover: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self.icon_factory = icon_factory
        self._get_metadata = get_metadata
        self._owned_status = owned_status
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_add = on_add
        self._on_select = on_select
        self._on_hover = on_hover
        self.cards: list[dict[str, Any]] = []
        self.card_widgets: list[CardBoxPanel] = []
        self.active_panel: CardBoxPanel | None = None
        self.selected_name: str | None = None

        self.SetBackgroundColour(DARK_PANEL)
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        header = wx.BoxSizer(wx.HORIZONTAL)
        self.count_label = wx.StaticText(self, label="0 cards")
        self.count_label.SetForegroundColour(SUBDUED_TEXT)
        header.Add(self.count_label, 0, wx.ALIGN_CENTER_VERTICAL)
        header.AddStretchSpacer(1)
        outer.Add(header, 0, wx.EXPAND | wx.BOTTOM, 4)

        self.scroller = scrolled.ScrolledPanel(self, style=wx.VSCROLL)
        self.scroller.SetBackgroundColour(DARK_PANEL)
        self.grid_sizer = wx.GridSizer(0, 4, 8, 8)
        self.scroller.SetSizer(self.grid_sizer)
        self.scroller.SetupScrolling(scroll_x=False, scroll_y=True, rate_x=5, rate_y=5)
        outer.Add(self.scroller, 1, wx.EXPAND)

    def set_cards(self, cards: list[dict[str, Any]]) -> None:
        if self._try_incremental_update(cards):
            self.cards = cards
            return
        self.cards = cards
        self._rebuild_grid()

    def _try_incremental_update(self, new_cards: list[dict[str, Any]]) -> bool:
        """Try to update existing widgets incrementally instead of rebuilding.
        Returns True if incremental update was possible, False if full rebuild needed."""
        if len(new_cards) != len(self.card_widgets):
            return False

        # Check if cards match widgets in the same order
        # (new_cards may have been sorted while widgets are in old order)
        for widget, new_card in zip(self.card_widgets, new_cards):
            if widget.card["name"].lower() != new_card["name"].lower():
                return False

        # All cards match widget order - update only changed quantities
        total = 0
        for widget, new_card in zip(self.card_widgets, new_cards):
            qty = new_card["qty"]
            total += qty

            # Only update widget if quantity or ownership color changed
            # Compare against widget's current displayed value to detect changes
            current_qty_str = widget.qty_label.GetLabel()
            if current_qty_str != str(qty):
                widget.card = new_card
                owned_text, owned_colour = self._owned_status(new_card["name"], int(qty))
                widget.update_quantity(qty, owned_text, owned_colour)
            else:
                # Still need to update card reference even if qty didn't change
                widget.card = new_card

        self.count_label.SetLabel(f"{total} card{'s' if total != 1 else ''}")
        return True

    def _rebuild_grid(self) -> None:
        self.scroller.Freeze()
        try:
            self.grid_sizer.Clear(delete_windows=True)
            self.card_widgets = []
            self.active_panel = None
            total = sum(card["qty"] for card in self.cards)
            self.count_label.SetLabel(f"{total} card{'s' if total != 1 else ''}")
            for card in self.cards:
                cell = CardBoxPanel(
                    self.scroller,
                    self.zone,
                    card,
                    self.icon_factory,
                    self._get_metadata,
                    self._owned_status,
                    self._on_delta,
                    self._on_remove,
                    self._handle_card_click,
                    self._on_hover,
                )
                self.grid_sizer.Add(cell, 0, wx.EXPAND)
                self.card_widgets.append(cell)
            remainder = len(self.cards) % 4
            if remainder:
                for _ in range(4 - remainder):
                    spacer = wx.Panel(self.scroller)
                    spacer.SetBackgroundColour(DARK_PANEL)
                    self.grid_sizer.Add(spacer, 0, wx.EXPAND)
            self.grid_sizer.Layout()
            self.scroller.Layout()
            self.scroller.FitInside()
            self.scroller.SetupScrolling(scroll_x=False, scroll_y=True, rate_x=5, rate_y=5)
            self._restore_selection()
        finally:
            self.scroller.Thaw()

    def _handle_card_click(self, zone: str, card: dict[str, Any], panel: CardBoxPanel) -> None:
        if self.active_panel is panel:
            self.clear_selection()
            return
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = panel
        self.selected_name = card["name"]
        panel.set_active(True)
        self._notify_selection(card)

    def _restore_selection(self) -> None:
        if not self.selected_name:
            self._notify_selection(None)
            return
        for widget in self.card_widgets:
            if widget.card["name"].lower() == self.selected_name.lower():
                self.active_panel = widget
                widget.set_active(True)
                self._notify_selection(widget.card)
                return
        previously_had_selection = self.selected_name is not None
        self.selected_name = None
        if previously_had_selection:
            self._notify_selection(None)

    def get_selected_card(self) -> dict[str, Any] | None:
        """Return the currently selected card in this table, if any."""
        if self.active_panel:
            return self.active_panel.card
        return None

    def focus_card(self, card_name: str) -> bool:
        """Programmatically focus the given card by name."""
        if not card_name:
            return False
        match = None
        for widget in self.card_widgets:
            if widget.card["name"].lower() == card_name.lower():
                match = widget
                break
        if match is None:
            return False
        if self.active_panel and self.active_panel is not match:
            self.active_panel.set_active(False)
        self.active_panel = match
        self.selected_name = match.card["name"]
        match.set_active(True)
        self.scroller.ScrollChildIntoView(match)
        self._notify_selection(match.card)
        return True

    def clear_selection(self) -> None:
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = None
        self.selected_name = None
        self._notify_selection(None)

    def collapse_active(self) -> None:
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = None
        self.selected_name = None

    def _notify_selection(self, card: dict[str, Any] | None) -> None:
        if self._on_select:
            self._on_select(self.zone, card)
