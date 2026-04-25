"""Deck notes panel UI construction package.

The :class:`DeckNotesPanel` itself owns the panel state and constructs the
toolbar + scrollable cards area, while :mod:`note_card_widget` defines the
individual styled note card and the note-data shape/migration helpers.

Re-exports :class:`_NoteCardWidget`, :func:`_new_card`, :func:`_migrate`, and
``NOTE_TYPES`` so existing
``from widgets.panels.deck_notes_panel.frame import _NoteCardWidget`` (etc.)
import sites continue to work.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_ALT, DARK_PANEL, SUBDUED_TEXT
from utils.stylize import stylize_button
from widgets.panels.deck_notes_panel.frame.note_card_widget import (
    NOTE_TYPES,
    _migrate,
    _new_card,
    _NoteCardWidget,
)
from widgets.panels.deck_notes_panel.handlers import DeckNotesPanelHandlersMixin
from widgets.panels.deck_notes_panel.properties import DeckNotesPanelPropertiesMixin

if TYPE_CHECKING:
    from repositories.deck_repository import DeckRepository
    from services.store_service import StoreService


class DeckNotesPanel(
    DeckNotesPanelHandlersMixin,
    DeckNotesPanelPropertiesMixin,
    wx.Panel,
):
    """Panel for structured deck notes composed of individual note cards."""

    def __init__(
        self,
        parent: wx.Window,
        deck_repo: DeckRepository,
        store_service: StoreService,
        notes_store: dict,
        notes_store_path: Path,
        on_status_update: Callable[[str], None],
        locale: str | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale

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

        add_btn = wx.Button(self, label=self._t("notes.btn.add"))
        stylize_button(add_btn)
        add_btn.Bind(wx.EVT_BUTTON, self._on_add_note)
        toolbar.Add(add_btn, 0, wx.RIGHT, 6)

        toolbar.AddStretchSpacer(1)

        self.save_btn = wx.Button(self, label=self._t("notes.btn.save"))
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

        self.empty_state_panel = wx.Panel(self)
        self.empty_state_panel.SetBackgroundColour(DARK_ALT)
        empty_sizer = wx.BoxSizer(wx.VERTICAL)
        self.empty_state_panel.SetSizer(empty_sizer)
        empty_sizer.AddStretchSpacer(1)
        empty_label = wx.StaticText(
            self.empty_state_panel,
            label=self._t("notes.empty"),
            style=wx.ALIGN_CENTRE_HORIZONTAL,
        )
        empty_label.SetForegroundColour(SUBDUED_TEXT)
        empty_sizer.Add(empty_label, 0, wx.ALIGN_CENTER | wx.ALL, 12)
        empty_sizer.AddStretchSpacer(1)
        self.empty_state_panel.Hide()
        outer.Add(self.empty_state_panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)


__all__ = [
    "NOTE_TYPES",
    "DeckNotesPanel",
    "_NoteCardWidget",
    "_migrate",
    "_new_card",
]
