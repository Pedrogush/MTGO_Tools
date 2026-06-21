"""Zone editing / deck-state mutation handlers."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import wx

from utils.constants import ZONE_TITLES

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class ZoneEditingHandlers(_Base):
    """Mutate deck zones and re-render tables, deck text, and stats."""

    def _after_zone_change(self, zone: str) -> None:
        if zone == "main":
            self.main_table.set_cards(self.zone_cards["main"], preserve_scroll=True)
        elif zone == "side":
            self.side_table.set_cards(self.zone_cards["side"], preserve_scroll=True)
        else:
            if self.out_table:
                self.out_table.set_cards(self.zone_cards["out"], preserve_scroll=True)
            self._persist_outboard_for_current()
        deck_text = self.controller.deck_service.build_deck_text_from_zones(self.zone_cards)
        self.controller.deck_repo.set_current_deck_text(deck_text)
        self._update_stats(deck_text)
        self.copy_button.Enable(self._has_deck_loaded())
        self.save_button.Enable(self._has_deck_loaded())
        self._schedule_settings_save()

    def _handle_zone_delta(self: AppFrame, zone: str, name: str, delta: int) -> None:
        cards = self.zone_cards.get(zone, [])
        for entry in cards:
            if entry["name"].lower() == name.lower():
                current_qty = entry["qty"]
                if isinstance(current_qty, float) and not current_qty.is_integer():
                    current_qty = math.ceil(current_qty) if delta > 0 else math.floor(current_qty)
                entry["qty"] = max(0, current_qty + delta)
                if entry["qty"] == 0:
                    cards.remove(entry)
                break
        else:
            if delta > 0:
                cards.append({"name": name, "qty": delta})
        cards.sort(key=lambda item: item["name"].lower())
        self.zone_cards[zone] = cards
        self._after_zone_change(zone)

    def _handle_zone_remove(self: AppFrame, zone: str, name: str) -> None:
        cards = self.zone_cards.get(zone, [])
        self.zone_cards[zone] = [entry for entry in cards if entry["name"].lower() != name.lower()]
        self._after_zone_change(zone)

    def _handle_zone_add(self: AppFrame, zone: str) -> None:
        if zone == "out":
            main_cards = [entry["name"] for entry in self.zone_cards.get("main", [])]
            existing = {entry["name"].lower() for entry in self.zone_cards.get("out", [])}
            candidates = [name for name in main_cards if name.lower() not in existing]
            if not candidates:
                wx.MessageBox(
                    "All mainboard cards are already in the outboard list.",
                    "Outboard",
                    wx.OK | wx.ICON_INFORMATION,
                )
                return
            dlg = wx.SingleChoiceDialog(
                self, "Select a mainboard card eligible for sideboarding.", "Outboard", candidates
            )
            if dlg.ShowModal() != wx.ID_OK:
                dlg.Destroy()
                return
            selection = dlg.GetStringSelection()
            dlg.Destroy()
            qty = next(
                (entry["qty"] for entry in self.zone_cards["main"] if entry["name"] == selection), 1
            )
            self.zone_cards.setdefault("out", []).append({"name": selection, "qty": qty})
            self.zone_cards["out"].sort(key=lambda item: item["name"].lower())
            self._after_zone_change("out")
            return

        dlg = wx.TextEntryDialog(
            self, f"Add card to {ZONE_TITLES.get(zone, zone)} (format: 'Qty Card Name')", "Add Card"
        )
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        value = dlg.GetValue().strip()
        dlg.Destroy()
        if not value:
            return
        parts = value.split(" ", 1)
        try:
            qty = int(parts[0]) if len(parts) > 1 else 1
        except ValueError:
            qty = 1
        name = parts[1].strip() if len(parts) > 1 else value
        if not name:
            return
        self.zone_cards.setdefault(zone, []).append({"name": name, "qty": max(1, qty)})
        self.zone_cards[zone].sort(key=lambda item: item["name"].lower())
        self._after_zone_change(zone)

    def _handle_zone_transfer(
        self: AppFrame, source_zone: str, names: list[str], screen_point: wx.Point
    ) -> bool:
        """Move dragged cards to the other zone when dropped over its pane.

        Called by a card view when a drag is released; returns True when the drop
        landed on the sibling zone (so the view skips its within-zone reorder).
        One copy is moved per entry in ``names`` (the pile view repeats a name to
        move several copies). Routes through the normal zone-delta path so both
        zones' quantities — and the deck text / stats — update correctly (#781).
        """
        if source_zone not in {"main", "side"} or not names:
            return False
        dest_zone = "side" if source_zone == "main" else "main"
        dest_table = self._get_table_for_zone(dest_zone)
        if not dest_table or not dest_table.GetScreenRect().Contains(screen_point):
            return False
        for name in names:
            # Only move a copy that's actually present in the source zone.
            if any(c["name"].lower() == name.lower() for c in self.zone_cards.get(source_zone, [])):
                self._handle_zone_delta(source_zone, name, -1)
                self._handle_zone_delta(dest_zone, name, 1)
        self._active_deck_zone = dest_zone
        return True
