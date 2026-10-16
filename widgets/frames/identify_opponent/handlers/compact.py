"""Compact mode: swap the tracker window for the floating chip and back.

The tracker keeps running while it is hidden (the poll timer, the radar and the
guide all update as usual); the chip only reads from it. The chip's position,
its padlock and whether compact mode was on are saved with the rest of the
tracker config, so the next match starts the way the last one ended.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.mtgo_window import find_match_window_rect
from widgets.frames.identify_opponent.compact import (
    HoverSection,
    chip_face,
    hover_sections,
    initial_chip_position,
)
from widgets.frames.identify_opponent.compact_chip import CHIP_SIZE, OpponentChip

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class CompactModeMixin(_Base):
    """Compact-mode switching, the chip's state, and its hover card content."""

    def _ensure_chip(self) -> OpponentChip:
        if self._chip is None:
            # No parent: the chip must stay up when the main window (which owns
            # the tracker) is minimised during a match. It is destroyed with
            # the tracker instead (``_destroy_chip``).
            self._chip = OpponentChip(
                None,
                on_expand=self._exit_compact_mode,
                on_moved=self._on_chip_moved,
                on_lock_changed=self._on_chip_lock_changed,
                hover_content=self._chip_hover_content,
                locked_hint=self._t("tracker.chip.hint_locked"),
                unlocked_hint=self._t("tracker.chip.hint_unlocked"),
            )
            self._chip.set_locked(self._chip_locked)
        return self._chip

    def _enter_compact_mode(self) -> None:
        chip = self._ensure_chip()
        chip.set_face(chip_face(self.player_name, self.last_seen_decks))
        chip.show_at(self._chip_start_position())
        self._compact_mode = True
        self.Hide()
        self._persist_config_async()

    def _exit_compact_mode(self) -> None:
        self._compact_mode = False
        if self._chip is not None:
            self._chip.hide()
        self.Show()
        self.Raise()
        self._persist_config_async()

    def _chip_start_position(self) -> tuple[int, int]:
        """The saved spot, else a guess under the opponent's portrait."""
        match_rect = None
        if self._chip_position is None:
            match_rect = find_match_window_rect(self.player_name or None)
            if match_rect is None:
                match_rect = find_match_window_rect()
        display_idx = wx.Display.GetFromWindow(self)
        if display_idx == wx.NOT_FOUND:
            display_idx = 0
        area = wx.Display(display_idx).GetClientArea()
        tracker = self.GetScreenRect()
        position = initial_chip_position(
            chip_size=CHIP_SIZE,
            display_area=(area.x, area.y, area.width, area.height),
            saved=self._chip_position,
            match_window=match_rect,
            fallback_anchor=(tracker.x, tracker.y, tracker.width, tracker.height),
        )
        return position

    def _on_chip_moved(self, position: tuple[int, int]) -> None:
        self._chip_position = [position[0], position[1]]
        self._persist_config_async()

    def _on_chip_lock_changed(self, locked: bool) -> None:
        self._chip_locked = locked
        self._persist_config_async()

    def _refresh_chip(self) -> None:
        """Keep the chip's initials and status dot in step with the opponent."""
        if self._chip is not None:
            self._chip.set_face(chip_face(self.player_name, self.last_seen_decks))

    def _chip_hover_content(self) -> tuple[str, list[HoverSection]]:
        """What the hover card shows: the headline, the radar and the guide,
        read from the (hidden) tracker panes as they are right now."""
        sections = []
        for pane in (self.radar_panel, self.sideboard_panel):
            lines = list(pane.card_list.GetStrings())
            if not lines and pane.status_label.GetLabel():
                # Loading or error text ("Loading radar for ...") stands in for
                # the list while there is none.
                lines = [pane.status_label.GetLabel()]
            sections.append((pane._header_text, lines))
        return self._deck_label_text, hover_sections(sections)

    def _restore_compact_mode(self) -> None:
        """Start in compact mode if that is how the tracker was last left."""
        if self._compact_mode:
            self._enter_compact_mode()

    def _destroy_chip(self) -> None:
        if self._chip is not None:
            self._chip.Destroy()
            self._chip = None
