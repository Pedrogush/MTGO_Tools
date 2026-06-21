"""Handlers for card table interactions."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.constants import ZONE_TITLES

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto
    from widgets.panels.card_table_panel import CardTablePanel

    _Base = AppFrameProto
else:
    _Base = object


class CardTablesHandler(_Base):
    """Mixin containing zone editing and card focus handlers."""

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

    # ------------------------------------------------------------------ Keyboard shortcuts -------------------------------------------------
    def _on_hotkey(self: AppFrame, event: wx.KeyEvent) -> None:
        key_code = event.GetKeyCode()

        if key_code == wx.WXK_F1 and not event.ControlDown():
            self._open_help()
            return

        if not event.ControlDown():
            # Plain +/-/Delete edit the quantity of the currently selected deck
            # card in whatever view (grid/table/pile) is showing. Skipped while a
            # text field has focus so they don't clobber normal typing.
            if not self._typing_in_text_field():
                if key_code in (ord("+"), wx.WXK_NUMPAD_ADD, ord("=")):
                    if self._handle_increment_shortcut():
                        return
                elif key_code in (ord("-"), wx.WXK_NUMPAD_SUBTRACT):
                    if self._handle_decrement_shortcut():
                        return
                elif key_code in (wx.WXK_DELETE, wx.WXK_NUMPAD_DELETE):
                    if self._handle_remove_shortcut():
                        return
            event.Skip()
            return
        handled = False

        if key_code in (ord("D"), ord("d")):
            self._show_left_panel("builder")
            handled = True
        elif key_code in (ord("R"), ord("r")):
            self._show_left_panel("research")
            handled = True
        elif key_code in (ord("1"), wx.WXK_NUMPAD1):
            handled = self._handle_increment_shortcut()
        elif key_code in (ord("2"), wx.WXK_NUMPAD2):
            handled = self._handle_decrement_shortcut()

        if handled:
            return
        event.Skip()

    @staticmethod
    def _typing_in_text_field() -> bool:
        """True when keyboard focus is on an editable text control.

        Used to suppress the bare +/-/Delete deck-edit shortcuts while the user
        is typing in a search box, deck-name field, notes area, etc.
        """
        focused = wx.Window.FindFocus()
        return isinstance(focused, (wx.TextCtrl, wx.SearchCtrl, wx.ComboBox))

    def _handle_increment_shortcut(self: AppFrame) -> bool:
        selection = self._get_selected_zone_card()
        if selection:
            zone, card = selection
            self._handle_zone_delta(zone, card["name"], 1)
            self._focus_card_in_zone(zone, card["name"])
            return True

        search_card = self._get_selected_search_card()
        if search_card:
            zone = self._get_active_zone_for_add()
            name = search_card.get("name")
            if name:
                self._handle_zone_delta(zone, name, 1)
                self._focus_card_in_zone(zone, name)
                return True
        return False

    def _handle_decrement_shortcut(self: AppFrame) -> bool:
        selection = self._get_selected_zone_card()
        if selection is None:
            return False
        zone, card = selection
        if zone not in {"main", "side"}:
            return False
        self._handle_zone_delta(zone, card["name"], -1)
        self._focus_card_in_zone(zone, card["name"])
        return True

    def _handle_remove_shortcut(self: AppFrame) -> bool:
        """Remove the selected card from its zone entirely (the [Del] shortcut)."""
        selection = self._get_selected_zone_card()
        if selection is None:
            return False
        zone, card = selection
        self._handle_zone_remove(zone, card["name"])
        return True

    def _get_selected_zone_card(self: AppFrame) -> tuple[str, dict[str, Any]] | None:
        for zone, table in (
            ("main", self.main_table),
            ("side", self.side_table),
            ("out", self.out_table),
        ):
            if not table:
                continue
            selected = table.get_selected_card()
            if selected:
                return zone, selected
        return None

    def _get_selected_search_card(self: AppFrame) -> dict[str, Any] | None:
        if not self.builder_panel:
            return None
        return self.builder_panel.get_selected_result()

    def _has_selected_card(self: AppFrame) -> bool:
        return (
            self._get_selected_zone_card() is not None
            or self._get_selected_search_card() is not None
        )

    def _clear_zone_selections(self: AppFrame) -> None:
        for table in (self.main_table, self.side_table, self.out_table):
            if table:
                table.clear_selection()

    def _get_active_zone_for_add(self: AppFrame) -> str:
        # Mainboard and sideboard are visible at once (#781), so there is no
        # active tab to disambiguate; use the zone the user last interacted with.
        zone = getattr(self, "_active_deck_zone", "main")
        return zone if zone in {"main", "side"} else "main"

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

    def _add_search_card_to_active_zone(self: AppFrame, name: str) -> None:
        zone = self._get_active_zone_for_add()
        self._handle_zone_delta(zone, name, 1)
        self._focus_card_in_zone(zone, name)

    def _focus_card_in_zone(self: AppFrame, zone: str, card_name: str) -> None:
        table = self._get_table_for_zone(zone)
        if not table:
            return
        self._collapse_other_zone_tables(zone)
        table.focus_card(card_name)

    def _get_table_for_zone(self: AppFrame, zone: str) -> CardTablePanel | None:
        if zone == "main":
            return self.main_table
        if zone == "side":
            return self.side_table
        if zone == "out":
            return self.out_table
        return None

    def _collapse_other_zone_tables(self, active_zone: str) -> None:
        tables = {
            "main": self.main_table,
            "side": self.side_table,
            "out": self.out_table,
        }
        for zone, table in tables.items():
            if zone == active_zone:
                continue
            if table:
                table.collapse_active()

    def _handle_card_focus(self: AppFrame, zone: str, card: dict[str, Any] | None) -> None:
        if card is None:
            if self.card_inspector_panel.active_zone == zone:
                self.card_inspector_panel.reset()
                self.card_panel.clear()
            return
        if zone in {"main", "side"}:
            self._active_deck_zone = zone
        if self.builder_panel:
            self.builder_panel.clear_result_selection()
        self._collapse_other_zone_tables(zone)
        meta = self.controller.card_repo.get_card_metadata(card["name"])
        selection = self._printing_selections.get(card["name"].lower())
        self.card_inspector_panel.update_card(card, zone=zone, meta=meta, selection=selection)
        self._push_card_panel(card, meta)

    # ---- printing selection (issue #792) --------------------------------------
    def _get_printing_image(self: AppFrame, name: str):
        """Resolve the chosen printing's board image for ``name``.

        Returns the cached image path for the card's selected printing, or
        ``None`` when no printing is selected (board falls back to the default
        art) or its image is not cached yet — in which case a download for that
        exact printing is queued so a later ``refresh_card_image`` picks it up.
        Runs on the view's image-decode threads; only SQLite reads + an enqueue.
        """
        selection = self._printing_selections.get(name.lower())
        if not selection:
            return None
        uuid = selection.get("uuid")
        set_code = selection.get("set")
        cache = self.controller.get_image_cache()
        path = cache.get_image_by_uuid(uuid, "normal") if uuid else None
        if path is None and set_code:
            path = cache.get_image_path_for_printing(name, set_code, "normal")
        if path is not None:
            return path
        try:
            request = self.controller.CardImageRequest(
                card_name=name,
                uuid=uuid,
                set_code=set_code,
                collector_number=None,
                size="normal",
            )
            self.controller.image_service.queue_card_image_download(request, prioritize=True)
        except Exception:
            logger.debug("Failed to queue printing image for %s", name, exc_info=True)
        return None

    def _on_inspector_printing_selected(
        self: AppFrame, printing: dict[str, Any], persist: bool
    ) -> None:
        """Apply (and optionally persist) a printing the user chose in the inspector.

        Always updates the runtime selection map + board art (issue #792, part
        1a); ``persist`` also writes the choice into the deck text so it survives
        save/copy (part 2 — auto-save or the Save-art button).
        """
        name = self.card_inspector_panel.inspector_current_card_name
        if not name or not printing:
            return
        self._record_printing_selection(name, printing)
        if persist:
            self._persist_printing_selection(name, printing)

    def _refresh_board_card_art(self: AppFrame, name: str) -> None:
        """Re-render just ``name``'s art across every zone after a selection change."""
        for table in (self.main_table, self.side_table, self.out_table):
            if table:
                table.refresh_card_image(name)

    def _record_printing_selection(self: AppFrame, name: str, printing: dict[str, Any]) -> None:
        """Update the runtime selection map and refresh that card's board art."""
        if not name:
            return
        self._printing_selections[name.lower()] = {
            "uuid": printing.get("id"),
            "set": printing.get("set"),
        }
        self._refresh_board_card_art(name)

    def _persist_printing_selection(self: AppFrame, name: str, printing: dict[str, Any]) -> None:
        """Write a printing choice into the canonical deck text so it survives.

        Saving / copying the deck reads ``current_deck_text`` (see
        ``build_deck_text``), so merging the chosen printing-id pointer there is
        what makes the choice persist into the exported decklist (issue #792,
        part 2). No-op when the printing index has not loaded.
        """
        if not name:
            return
        index = getattr(self.controller.image_service, "bulk_data_by_name", None)
        if not index:
            return
        deck_text = self.controller.deck_repo.get_current_deck_text()
        if not deck_text or not deck_text.strip():
            return
        merged = self.controller.deck_service.merge_printing_selection(
            deck_text, index, name, printing.get("id"), printing.get("set")
        )
        self.controller.deck_repo.set_current_deck_text(merged)

    def _handle_card_hover(self: AppFrame, zone: str, card: dict[str, Any]) -> None:
        if self._has_selected_card():
            return
        self._pending_hover = (zone, card)
        if self._inspector_hover_timer is None:
            self._inspector_hover_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_hover_preview, self._inspector_hover_timer)
        elif self._inspector_hover_timer.IsRunning():
            self._inspector_hover_timer.Stop()
        # Debounce inspector updates to avoid thrashing while the mouse moves quickly.
        self._inspector_hover_timer.StartOnce(120)

    def _flush_hover_preview(self: AppFrame, _event: wx.TimerEvent) -> None:
        if not self._pending_hover:
            return
        if self._has_selected_card():
            self._pending_hover = None
            return
        zone, card = self._pending_hover
        self._pending_hover = None
        meta = self.controller.card_repo.get_card_metadata(card["name"])
        selection = self._printing_selections.get(card["name"].lower())
        self.card_inspector_panel.update_card(card, zone=zone, meta=meta, selection=selection)
        self._push_card_panel(card, meta)

    def _push_card_panel(self: AppFrame, card: dict[str, Any], meta: Any) -> None:
        """Forward the current card+printing+context to :attr:`card_panel`."""
        printing = self._current_inspector_printing()
        # Pass meta verbatim — both dicts and ``CardEntry`` work with the
        # panel's renderer (it only uses ``.get(key)``).
        self.card_panel.update_card(meta, printing=printing)

    def _current_inspector_printing(self: AppFrame) -> dict[str, Any] | None:
        printings = getattr(self.card_inspector_panel, "inspector_printings", None) or []
        idx = getattr(self.card_inspector_panel, "inspector_current_printing", 0)
        if not printings:
            return None
        try:
            entry = printings[idx]
        except IndexError:
            return None
        # Entries may be msgspec PrintingEntry structs or plain dicts.
        if isinstance(entry, dict):
            return entry
        if hasattr(entry, "get"):
            keys = (
                "id",
                "set",
                "set_name",
                "collector_number",
                "released_at",
                "flavor_text",
                "artist",
            )
            return {key: entry.get(key) for key in keys}
        return None
