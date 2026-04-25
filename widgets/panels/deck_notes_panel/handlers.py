"""Event handlers, public state setters, and UI populators for the deck notes panel."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import wx
from loguru import logger

if TYPE_CHECKING:
    from repositories.deck_repository import DeckRepository
    from services.store_service import StoreService
    from widgets.panels.deck_notes_panel.frame import _NoteCardWidget


class DeckNotesPanelHandlersMixin:
    """Public setters, event callbacks, and card-list population for :class:`DeckNotesPanel`."""

    deck_repo: DeckRepository
    store_service: StoreService
    notes_store: dict
    notes_store_path: Path
    on_status_update: Callable[[str], None]
    _locale: str | None
    _cards: list[dict[str, str]]
    _card_widgets: list[_NoteCardWidget]
    scroll_win: wx.ScrolledWindow
    cards_sizer: wx.BoxSizer
    empty_state_panel: wx.Panel

    # ═══════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════

    def set_notes(self, notes: list[dict[str, str]] | str) -> None:
        from widgets.panels.deck_notes_panel.frame import _migrate

        self._cards = _migrate(notes)
        self._rebuild_card_widgets()

    def clear(self) -> None:
        self._cards = []
        self._rebuild_card_widgets()

    def load_notes_for_current(self) -> None:
        deck_key = self.deck_repo.get_current_deck_key()
        raw = self.notes_store.get(deck_key, [])
        logger.info(
            "Loading deck notes: deck_key={} found={} note_count={}",
            deck_key,
            deck_key in self.notes_store,
            len(raw) if isinstance(raw, list) else int(bool(raw)),
        )
        self.set_notes(raw)

    def save_current_notes(self) -> None:
        deck_key = self.deck_repo.get_current_deck_key()
        self.notes_store[deck_key] = self.get_notes()
        self.store_service.save_store(self.notes_store_path, self.notes_store)
        self.on_status_update("notes.saved")

    # ═══════════════════════════════════════════════════════════════════════
    # Private helpers
    # ═══════════════════════════════════════════════════════════════════════

    def _rebuild_card_widgets(self) -> None:
        self.scroll_win.Freeze()
        for w in self._card_widgets:
            w.Destroy()
        self._card_widgets = []
        self.cards_sizer.Clear(delete_windows=False)  # already destroyed above

        for card in self._cards:
            widget = self._make_card_widget(card)
            self._card_widgets.append(widget)
            self.cards_sizer.Add(widget, 0, wx.EXPAND | wx.ALL, 4)

        has_cards = bool(self._cards)
        self.scroll_win.Show(has_cards)
        self.empty_state_panel.Show(not has_cards)
        self.cards_sizer.Layout()
        self.scroll_win.Layout()
        self.scroll_win.FitInside()
        self.scroll_win.Thaw()
        self.Layout()

    def _make_card_widget(self, card: dict[str, str]) -> _NoteCardWidget:
        from widgets.panels.deck_notes_panel.frame import _NoteCardWidget

        return _NoteCardWidget(
            self.scroll_win,
            card,
            on_move_up=self._on_card_move_up,
            on_move_down=self._on_card_move_down,
            on_delete=self._on_card_delete,
            locale=self._locale,
        )

    def _flush_widgets_to_cards(self) -> None:
        self._cards = [w.get_data() for w in self._card_widgets]

    def _on_add_note(self, _event: wx.Event) -> None:
        from widgets.panels.deck_notes_panel.frame import _new_card

        self._flush_widgets_to_cards()
        self._cards.append(_new_card())
        self._rebuild_card_widgets()
        # Scroll to bottom so the new card is visible
        self.scroll_win.Scroll(0, self.scroll_win.GetVirtualSize().height)

    def _on_card_move_up(self, widget: _NoteCardWidget) -> None:
        self._flush_widgets_to_cards()
        idx = self._card_widgets.index(widget)
        if idx > 0:
            self._cards[idx - 1], self._cards[idx] = (
                self._cards[idx],
                self._cards[idx - 1],
            )
            self._rebuild_card_widgets()

    def _on_card_move_down(self, widget: _NoteCardWidget) -> None:
        self._flush_widgets_to_cards()
        idx = self._card_widgets.index(widget)
        if idx < len(self._cards) - 1:
            self._cards[idx], self._cards[idx + 1] = (
                self._cards[idx + 1],
                self._cards[idx],
            )
            self._rebuild_card_widgets()

    def _on_card_delete(self, widget: _NoteCardWidget) -> None:
        self._flush_widgets_to_cards()
        idx = self._card_widgets.index(widget)
        self._cards.pop(idx)
        self._rebuild_card_widgets()

    def _on_save_clicked(self, _event: wx.Event) -> None:
        self.save_current_notes()
