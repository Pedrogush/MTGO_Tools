"""Manual archetype loading and sideboard-guide display for the opponent tracker.

Lets the user pin an archetype by hand (bypassing opponent detection) and keeps
the compact sideboard-guide panel in sync with the currently tracked archetype.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants import (
    ACTIVE_GUIDE_FILE,
    GUIDE_STORE,
    OPPONENT_TRACKER_LABEL_WRAP_WIDTH,
)

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class ManualArchetypeMixin(_Base):
    """Manual archetype selection and sideboard-guide rendering."""

    def _on_load_archetype_clicked(self, _event: wx.CommandEvent) -> None:
        """Open dialog to manually load an archetype for radar/guide lookup."""
        # Local import to avoid a circular dependency between frame.py and handlers.py.
        from widgets.frames.identify_opponent.frame import _LoadArchetypeDialog

        if self._manual_archetype_loaded:
            self._unload_manual_archetype()
            return

        dlg = _LoadArchetypeDialog(
            self,
            title=self._t("tracker.dlg.load_archetype.title"),
            format_label=self._t("tracker.dlg.load_archetype.format"),
            archetype_label=self._t("tracker.dlg.load_archetype.archetype"),
            metagame_service=self.metagame_service,
            locale=self._locale,
        )
        if dlg.ShowModal() == wx.ID_OK:
            fmt, archetype = dlg.get_values()
            if fmt and archetype:
                self._load_archetype_manually(fmt, archetype)
        dlg.Destroy()

    def _update_guide_display(self) -> None:
        if not self.last_seen_decks:
            self.sideboard_panel.clear()
            return

        _format_name, archetype_name = next(iter(self.last_seen_decks.items()))
        if not archetype_name or archetype_name == "Unknown":
            self.sideboard_panel.clear()
            return

        # Load pinned guide
        if not ACTIVE_GUIDE_FILE.exists():
            self.sideboard_panel.set_no_pinned_deck()
            return

        try:
            with ACTIVE_GUIDE_FILE.open("r", encoding="utf-8") as fh:
                active = json.load(fh)
        except Exception as exc:
            logger.warning(f"Failed to read active guide file: {exc}")
            self.sideboard_panel.set_no_pinned_deck()
            return

        deck_hash = active.get("deck_hash", "")
        if not deck_hash:
            self.sideboard_panel.set_no_pinned_deck()
            return

        # Load guide store
        try:
            if GUIDE_STORE.exists():
                with GUIDE_STORE.open("r", encoding="utf-8") as fh:
                    guide_store = json.load(fh)
            else:
                guide_store = {}
        except Exception as exc:
            logger.warning(f"Failed to read guide store: {exc}")
            guide_store = {}

        payload = guide_store.get(deck_hash) or {}
        entries: list[dict] = payload.get("entries", [])
        exclusions: list[str] = payload.get("exclusions", [])

        if not entries:
            self.sideboard_panel.set_no_guide(archetype_name)
            return

        # Find matching entry (case-insensitive substring match)
        archetype_lower = archetype_name.lower()
        match = None
        for entry in entries:
            entry_arch = entry.get("archetype", "")
            if entry_arch in exclusions:
                continue
            if entry_arch.lower() == archetype_lower:
                match = entry
                break
        if match is None:
            for entry in entries:
                entry_arch = entry.get("archetype", "")
                if entry_arch in exclusions:
                    continue
                if archetype_lower in entry_arch.lower() or entry_arch.lower() in archetype_lower:
                    match = entry
                    break

        if match is None:
            self.sideboard_panel.set_no_guide(archetype_name)
        else:
            self.sideboard_panel.display_entry(match, archetype_name)

    def _load_archetype_manually(self, fmt: str, archetype: str) -> None:
        """Load radar and guide for a manually specified archetype."""
        self._stop_watching()
        self._clear_radar_display()
        self._manual_archetype_loaded = True
        self.player_name = "(manual)"
        self.last_seen_decks = {fmt: archetype}
        self.deck_label.SetLabel(
            self._t("tracker.label.manual_archetype", archetype=archetype, fmt=fmt)
        )
        self.deck_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        self.status_label.SetLabel(self._t("tracker.status.manual_loaded"))
        self.status_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        self.load_arch_btn.SetLabel(self._t("tracker.btn.unload_archetype"))
        self._trigger_radar_load()
        self._update_guide_display()

    def _unload_manual_archetype(self) -> None:
        self._manual_archetype_loaded = False
        self.player_name = ""
        self.last_seen_decks = {}
        self.load_arch_btn.SetLabel(self._t("tracker.btn.load_archetype"))
        self._clear_radar_display()
        self._refresh_opponent_display()
        self._start_polling()
