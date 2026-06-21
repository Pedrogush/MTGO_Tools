"""Event callbacks, public state setters, and UI populators for the card table panel."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from utils.perf import perf_phase, timed

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
        zone = self.zone
        # Always refresh the count label irrespective of active view.
        with perf_phase(f"[{zone}] count/metadata loop ({len(cards)} cards)"):
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

        # Populate only the active view. Each view is fully rebuilt by its
        # set_cards (the grid blits bitmaps, the table issues ~5 SetCellValue
        # per card, the pile kicks off image loads), so rebuilding a hidden
        # view on every +/- edit just delays the visible view's refresh.
        # set_view_mode() re-populates whichever view becomes active on the next
        # switch, so a stale hidden view is harmless.
        if self.view_mode == "grid":
            with perf_phase(f"[{zone}] grid_view.set_cards"):
                self.grid_view.set_cards(cards, preserve_scroll)
        elif self.view_mode == "table":
            with perf_phase(f"[{zone}] table_view.set_cards"):
                self.table_view.set_cards(cards)
        elif self.view_mode == "pile":
            with perf_phase(f"[{zone}] pile_view.set_cards"):
                self.pile_view.set_cards(cards)

        self._switch_content_page()
        self._restore_selection()

    def _find_card(self, name: str) -> dict[str, Any] | None:
        for card in self.cards:
            if card["name"].lower() == name.lower():
                return card
        return None

    def _sync_selection(self) -> None:
        """Mirror ``selected_name`` into all three views so the highlight matches
        no matter which view is on top."""
        self.grid_view.set_selected(self.selected_name)
        self.table_view.set_selected(self.selected_name)
        self.pile_view.set_selected(self.selected_name)

    def _restore_selection(self) -> None:
        if not self.selected_name:
            self._sync_selection()
            self._notify_selection(None)
            return
        card = self._find_card(self.selected_name)
        if card is not None:
            self._sync_selection()
            self._notify_selection(card)
            return
        # Selected card is no longer in the zone — drop the selection.
        self.selected_name = None
        self._sync_selection()
        self._notify_selection(None)

    def focus_card(self, card_name: str) -> bool:
        if not card_name:
            return False
        card = self._find_card(card_name)
        if card is None:
            return False
        self.selected_name = card["name"]
        self._sync_selection()
        # Scroll the grid canvas to the card when it's the active view; the
        # table view scrolls itself via set_selected, the pile view doesn't.
        if self.view_mode == "grid":
            self.grid_view.focus_card(card["name"])
        self._notify_selection(card)
        return True

    def clear_selection(self) -> None:
        self.selected_name = None
        self._sync_selection()
        self._notify_selection(None)

    def collapse_active(self) -> None:
        self.selected_name = None
        self._sync_selection()

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
        for card in self.cards:
            if card["name"].lower() in face_keys:
                self.grid_view.refresh_image(card["name"])
                self.pile_view.refresh_image(card["name"])

    def _notify_selection(self, card: dict[str, Any] | None) -> None:
        if self._on_select:
            self._on_select(self.zone, card)
