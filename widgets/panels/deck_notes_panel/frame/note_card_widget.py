"""Single styled note card widget plus the note-data shape and migration helpers."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import wx

from utils.constants import DARK_ALT, DARK_BG, LIGHT_TEXT, SUBDUED_TEXT
from utils.i18n import translate
from utils.stylize import stylize_textctrl

NOTE_TYPES = ["General", "Matchup", "Sideboard Plan", "Custom"]

_NOTE_TYPE_I18N_KEYS: dict[str, str] = {
    "General": "notes.type.general",
    "Matchup": "notes.type.matchup",
    "Sideboard Plan": "notes.type.sideboard_plan",
    "Custom": "notes.type.custom",
}

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
        locale: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(DARK_BG)
        self.card_id = card["id"]
        self._locale = locale
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

        translated_types = [translate(locale, _NOTE_TYPE_I18N_KEYS.get(k, k)) for k in NOTE_TYPES]
        self.type_choice = wx.Choice(self, choices=translated_types)
        self.type_choice.SetBackgroundColour(DARK_ALT)
        self.type_choice.SetForegroundColour(LIGHT_TEXT)
        note_type = card.get("type", "General")
        idx = NOTE_TYPES.index(note_type) if note_type in NOTE_TYPES else 0
        self.type_choice.SetSelection(idx)
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
        return {
            "id": self.card_id,
            "title": self.title_ctrl.GetValue(),
            "body": self.body_ctrl.GetValue(),
            "type": NOTE_TYPES[self.type_choice.GetSelection()],
        }

    def _on_type_changed(self, _event: wx.Event) -> None:
        self._update_type_color()

    def _update_type_color(self) -> None:
        note_type = NOTE_TYPES[self.type_choice.GetSelection()]
        color = _TYPE_FG.get(note_type, LIGHT_TEXT)
        self.type_choice.SetForegroundColour(color)
        self.type_choice.Refresh()
