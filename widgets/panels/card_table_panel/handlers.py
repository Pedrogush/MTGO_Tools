"""Event callbacks, public state setters, and UI populators for the card table panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.perf import timed
from widgets.panels.card_box_panel import CardBoxPanel

if TYPE_CHECKING:
    from widgets.panels.card_table_panel.protocol import CardTablePanelProto

    _Base = CardTablePanelProto
else:
    _Base = object

_PAGE_EMPTY = 0
_PAGE_GRID = 1
_PAGE_TABLE = 2
_PAGE_PILE = 3
_PAGE_LOADING = 4


class CardTablePanelHandlersMixin(_Base):
    """Event callbacks, setters, and UI populators for :class:`CardTablePanel`."""

    def show_loading(self, label: str) -> None:
        self._loading_state._label.SetLabel(label)  # type: ignore[attr-defined]
        if self._content_book.GetSelection() != _PAGE_LOADING:
            self._content_book.ChangeSelection(_PAGE_LOADING)

    def set_cards(self, cards: list[dict[str, Any]], preserve_scroll: bool = False) -> None:
        self.cards = cards
        self._update_panels(cards, preserve_scroll)

    @timed
    def _update_panels(self, cards: list[dict[str, Any]], preserve_scroll: bool = False) -> None:
        self.Freeze()
        needs_image_load: list[CardBoxPanel] = []
        try:
            self.scroller.Freeze()
            try:
                # Always refresh the count label irrespective of active view.
                total = lands = mdfcs = 0
                for card in cards:
                    qty = card["qty"]
                    total += qty
                    meta = self._get_metadata(card["name"]) or {}
                    type_line = (meta.get("type_line") or "").lower()
                    back_type_line = (meta.get("back_type_line") or "").lower()
                    if "land" in type_line:
                        lands += qty
                    elif "land" in back_type_line:
                        mdfcs += qty
                label = f"{total} card{'s' if total != 1 else ''}"
                parts = []
                if lands:
                    parts.append(f"{lands} land{'s' if lands != 1 else ''}")
                if mdfcs:
                    parts.append(f"{mdfcs} MDFC{'s' if mdfcs != 1 else ''}")
                if parts:
                    label += " | " + " + ".join(parts)
                self.count_label.SetLabel(label)

                # Refresh the grid-view widget pool (still needed even when not
                # the active page, so the next switch is instant).
                if self.active_panel:
                    self.active_panel.set_active(False)
                self.active_panel = None
                # Grow the recycled pool on demand. Cells are allocated lazily
                # (see CardTablePanel._ensure_pool) so an empty deck creates no
                # grid cells at startup; this is where they actually appear.
                self._ensure_pool(len(cards))
                for i, panel in enumerate(self._pool):
                    if i < len(cards):
                        card = cards[i]
                        if panel.card is card:
                            panel.update_qty()
                        else:
                            panel.assign_card(card, self.zone)
                            needs_image_load.append(panel)
                        self.grid_sizer.Show(panel, True)
                    else:
                        self.grid_sizer.Show(panel, False)
                self.card_widgets = self._pool[: len(cards)]
                self.grid_sizer.Layout()
                self.scroller.Layout()
                self.scroller.FitInside()
                self.scroller.SetupScrolling(
                    scroll_x=False,
                    scroll_y=True,
                    rate_x=5,
                    rate_y=5,
                    scrollToTop=not preserve_scroll,
                )

                # Populate the table/pile views only when one of them is the
                # active page. Both are fully rebuilt by set_cards (the table
                # issues ~5 SetCellValue per card plus a column auto-size, the
                # pile kicks off image loads), so rebuilding the hidden view on
                # every +/- edit just delays the visible view's refresh.
                # set_view_mode() re-populates whichever view becomes active on
                # the next switch, so a stale hidden view is harmless.
                if self.view_mode == "table":
                    self.table_view.set_cards(cards)
                elif self.view_mode == "pile":
                    self.pile_view.set_cards(cards)

                self._switch_content_page()
                self._restore_selection()
            finally:
                self.scroller.Thaw()
        finally:
            self.Thaw()

        for panel in needs_image_load:
            panel.load_image_async()

    def _handle_card_click(self, zone: str, card: dict[str, Any], panel: CardBoxPanel) -> None:
        if self.active_panel is panel:
            self.clear_selection()
            return
        if self.active_panel:
            self.active_panel.set_active(False)
            self.active_panel.Update()
        self.active_panel = panel
        self.selected_name = card["name"]
        panel.set_active(True)
        self._sync_table_pile_selection()
        self._notify_selection(card)

    def _restore_selection(self) -> None:
        if not self.selected_name:
            self._sync_table_pile_selection()
            self._notify_selection(None)
            return
        for widget in self.card_widgets:
            if widget.card["name"].lower() == self.selected_name.lower():
                self.active_panel = widget
                widget.set_active(True)
                self._sync_table_pile_selection()
                self._notify_selection(widget.card)
                return
        previously_had_selection = self.selected_name is not None
        self.selected_name = None
        self._sync_table_pile_selection()
        if previously_had_selection:
            self._notify_selection(None)

    def _sync_table_pile_selection(self) -> None:
        # Mirror selection state into the table view and pile view so the
        # highlighted row/card matches no matter which view is on top.
        self.table_view.set_selected(self.selected_name)
        self.pile_view.set_selected(self.selected_name)

    def focus_card(self, card_name: str) -> bool:
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
        self._sync_table_pile_selection()
        self._notify_selection(match.card)
        return True

    def clear_selection(self) -> None:
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = None
        self.selected_name = None
        self._sync_table_pile_selection()
        self._notify_selection(None)

    def collapse_active(self) -> None:
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = None
        self.selected_name = None
        self._sync_table_pile_selection()

    def refresh_card_image(self, card_name: str) -> None:
        if not card_name:
            return
        key = card_name.lower()
        face_keys: set[str] = {key}
        if "//" in key:
            for part in key.split("//"):
                stripped = part.strip()
                if stripped:
                    face_keys.add(stripped)
        for widget in self.card_widgets:
            if widget.card["name"].lower() in face_keys:
                widget.refresh_image()  # resets state and triggers load_image_async()

    def _notify_selection(self, card: dict[str, Any] | None) -> None:
        if self._on_select:
            self._on_select(self.zone, card)
