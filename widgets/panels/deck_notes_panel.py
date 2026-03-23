"""
Deck Notes Panel - Structured note card editor for deck notes.

Each note is an individual card with a title, type, and body. Cards can be
added, edited, reordered, and deleted independently.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.constants import (
    DARK_ALT,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    SUBDUED_TEXT,
)
from utils.stylize import stylize_button, stylize_textctrl

if TYPE_CHECKING:
    from repositories.deck_repository import DeckRepository
    from services.store_service import StoreService

NOTE_TYPES = ["General", "Matchup", "Sideboard Plan", "Custom"]

# Per-type accent colors (foreground on the type label badge)
_TYPE_FG: dict[str, tuple[int, int, int]] = {
    "General": (59, 130, 246),
    "Matchup": (34, 197, 94),
    "Sideboard Plan": (168, 85, 247),
    "Custom": (251, 146, 60),
}


def _new_card(
    title: str = "",
    body: str = "",
    note_type: str = "General",
) -> dict[str, str]:
    return {"id": str(uuid.uuid4()), "title": title, "body": body, "type": note_type}


def _migrate(value: Any) -> list[dict[str, str]]:
    """Convert legacy string notes to the list-of-cards format."""
    if isinstance(value, str):
        return [_new_card(title="Notes", body=value)] if value.strip() else []
    if isinstance(value, list):
        return value
    return []


class _NoteCardWidget(wx.Panel):
    """A single styled note card with title, type selector, body, and action buttons."""

    def __init__(
        self,
        parent: wx.Window,
        card: dict[str, str],
        on_move_up: Callable[[_NoteCardWidget], None],
        on_move_down: Callable[[_NoteCardWidget], None],
        on_delete: Callable[[_NoteCardWidget], None],
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(DARK_BG)
        self.card_id = card["id"]
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down
        self._on_delete = on_delete

        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        # ── Header row ──────────────────────────────────────────────────────
        header = wx.BoxSizer(wx.HORIZONTAL)
        outer.Add(header, 0, wx.EXPAND | wx.ALL, 6)

        self.title_ctrl = wx.TextCtrl(self, value=card.get("title", ""))
        self.title_ctrl.SetBackgroundColour(DARK_ALT)
        self.title_ctrl.SetForegroundColour(LIGHT_TEXT)
        font = self.title_ctrl.GetFont()
        font.MakeBold()
        self.title_ctrl.SetFont(font)
        header.Add(self.title_ctrl, 1, wx.EXPAND | wx.RIGHT, 6)

        self.type_choice = wx.Choice(self, choices=NOTE_TYPES)
        self.type_choice.SetBackgroundColour(DARK_ALT)
        self.type_choice.SetForegroundColour(LIGHT_TEXT)
        note_type = card.get("type", "General")
        idx = self.type_choice.FindString(note_type)
        self.type_choice.SetSelection(max(idx, 0))
        self._update_type_color()
        self.type_choice.Bind(wx.EVT_CHOICE, self._on_type_changed)
        header.Add(self.type_choice, 0, wx.RIGHT, 6)

        up_btn = wx.Button(self, label="↑", size=(28, -1))
        down_btn = wx.Button(self, label="↓", size=(28, -1))
        del_btn = wx.Button(self, label="✕", size=(28, -1))
        for btn in (up_btn, down_btn, del_btn):
            btn.SetBackgroundColour(DARK_ALT)
            btn.SetForegroundColour(SUBDUED_TEXT)
        del_btn.SetForegroundColour((220, 80, 80))
        up_btn.Bind(wx.EVT_BUTTON, lambda _: self._on_move_up(self))
        down_btn.Bind(wx.EVT_BUTTON, lambda _: self._on_move_down(self))
        del_btn.Bind(wx.EVT_BUTTON, lambda _: self._on_delete(self))
        header.Add(up_btn, 0, wx.RIGHT, 2)
        header.Add(down_btn, 0, wx.RIGHT, 6)
        header.Add(del_btn, 0)

        # ── Body ────────────────────────────────────────────────────────────
        self.body_ctrl = wx.TextCtrl(
            self,
            value=card.get("body", ""),
            style=wx.TE_MULTILINE | wx.TE_BESTWRAP,
        )
        self.body_ctrl.SetMinSize((-1, 80))
        stylize_textctrl(self.body_ctrl, multiline=True)
        outer.Add(self.body_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

    def get_data(self) -> dict[str, str]:
        """Return current card data from widget values."""
        return {
            "id": self.card_id,
            "title": self.title_ctrl.GetValue(),
            "body": self.body_ctrl.GetValue(),
            "type": self.type_choice.GetString(self.type_choice.GetSelection()),
        }

    def _on_type_changed(self, _event: wx.Event) -> None:
        self._update_type_color()

    def _update_type_color(self) -> None:
        note_type = self.type_choice.GetString(self.type_choice.GetSelection())
        color = _TYPE_FG.get(note_type, LIGHT_TEXT)
        self.type_choice.SetForegroundColour(color)
        self.type_choice.Refresh()


class DeckNotesPanel(wx.Panel):
    """Panel for structured deck notes composed of individual note cards."""

    def __init__(
        self,
        parent: wx.Window,
        deck_repo: DeckRepository,
        store_service: StoreService,
        notes_store: dict,
        notes_store_path: Path,
        on_status_update: Callable[[str], None],
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)

        self.deck_repo = deck_repo
        self.store_service = store_service
        self.notes_store = notes_store
        self.notes_store_path = notes_store_path
        self.on_status_update = on_status_update

        self._cards: list[dict[str, str]] = []
        self._card_widgets: list[_NoteCardWidget] = []

        self._build_ui()

    def _build_ui(self) -> None:
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        # ── Toolbar ─────────────────────────────────────────────────────────
        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        outer.Add(toolbar, 0, wx.EXPAND | wx.ALL, 6)

        add_btn = wx.Button(self, label="+ Add Note")
        stylize_button(add_btn)
        add_btn.Bind(wx.EVT_BUTTON, self._on_add_note)
        toolbar.Add(add_btn, 0, wx.RIGHT, 6)

        toolbar.AddStretchSpacer(1)

        self.save_btn = wx.Button(self, label="Save Notes")
        stylize_button(self.save_btn)
        self.save_btn.Bind(wx.EVT_BUTTON, self._on_save_clicked)
        toolbar.Add(self.save_btn, 0)

        # ── Scrollable cards area ────────────────────────────────────────────
        self.scroll_win = wx.ScrolledWindow(self, style=wx.VSCROLL)
        self.scroll_win.SetScrollRate(0, 12)
        self.scroll_win.SetBackgroundColour(DARK_PANEL)
        outer.Add(self.scroll_win, 1, wx.EXPAND)

        self.cards_sizer = wx.BoxSizer(wx.VERTICAL)
        self.scroll_win.SetSizer(self.cards_sizer)

    # ═══════════════════════════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════════════════════════

    def set_notes(self, notes: list[dict[str, str]] | str) -> None:
        """Load note cards from storage data (list-of-cards or legacy string)."""
        self._cards = _migrate(notes)
        self._rebuild_card_widgets()

    def get_notes(self) -> list[dict[str, str]]:
        """Return current card data from all widgets."""
        return [w.get_data() for w in self._card_widgets]

    def clear(self) -> None:
        """Remove all note cards."""
        self._cards = []
        self._rebuild_card_widgets()

    def load_notes_for_current(self) -> None:
        """Load notes for the currently selected deck."""
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
        """Persist note cards for the currently selected deck."""
        deck_key = self.deck_repo.get_current_deck_key()
        self.notes_store[deck_key] = self.get_notes()
        self.store_service.save_store(self.notes_store_path, self.notes_store)
        self.on_status_update("Deck notes saved.")

    # ═══════════════════════════════════════════════════════════════════════
    # Private helpers
    # ═══════════════════════════════════════════════════════════════════════

    def _rebuild_card_widgets(self) -> None:
        """Destroy all card widgets and recreate them from self._cards."""
        self.scroll_win.Freeze()
        for w in self._card_widgets:
            w.Destroy()
        self._card_widgets = []
        self.cards_sizer.Clear(delete_windows=False)  # already destroyed above

        for card in self._cards:
            widget = self._make_card_widget(card)
            self._card_widgets.append(widget)
            self.cards_sizer.Add(widget, 0, wx.EXPAND | wx.ALL, 4)

        self.cards_sizer.Layout()
        self.scroll_win.Layout()
        self.scroll_win.FitInside()
        self.scroll_win.Thaw()

    def _make_card_widget(self, card: dict[str, str]) -> _NoteCardWidget:
        return _NoteCardWidget(
            self.scroll_win,
            card,
            on_move_up=self._on_card_move_up,
            on_move_down=self._on_card_move_down,
            on_delete=self._on_card_delete,
        )

    def _flush_widgets_to_cards(self) -> None:
        """Sync self._cards from current widget values (before reorder/delete)."""
        self._cards = [w.get_data() for w in self._card_widgets]

    def _on_add_note(self, _event: wx.Event) -> None:
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
