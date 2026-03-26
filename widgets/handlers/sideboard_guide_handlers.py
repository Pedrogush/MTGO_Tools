"""Sideboard guide and outboard handlers for the deck selector frame."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.atomic_io import atomic_write_json
from utils.constants import ACTIVE_GUIDE_FILE
from utils.constants.app import DECK_HASH_DISPLAY_LENGTH
from utils.constants.ui_layout import PADDING_BASE, PADDING_XL
from utils.constants.ui_windows import (
    GUIDE_IMPORT_OPTIONS_DIALOG_HEIGHT,
    GUIDE_IMPORT_OPTIONS_DIALOG_WIDTH,
)
from widgets.dialogs.guide_entry_dialog import GuideEntryDialog

if TYPE_CHECKING:
    from widgets.app_frame import AppFrame


class SideboardGuideHandlers:
    """Mixin that centralizes guide/outboard interactions for the deck selector."""

    def _persist_outboard_for_current(self: AppFrame) -> None:
        key = self.controller.deck_repo.get_current_deck_key()
        self.controller.outboard_store[key] = self.zone_cards.get("out", [])
        self.controller.store_service.save_store(
            self.controller.outboard_store_path, self.controller.outboard_store
        )

    def _load_outboard_for_current(self: AppFrame) -> list[dict[str, Any]]:
        key = self.controller.deck_repo.get_current_deck_key()
        data = self.controller.outboard_store.get(key, [])
        cleaned: list[dict[str, Any]] = []
        for entry in data:
            name = entry.get("name")
            qty_raw = entry.get("qty", 0)
            try:
                qty_float = float(qty_raw)
                qty = int(qty_float) if qty_float.is_integer() else qty_float
            except (TypeError, ValueError):
                qty = 0
            if name and qty > 0:
                cleaned.append({"name": name, "qty": qty})
        return cleaned

    def _refresh_pin_indicator(self: AppFrame) -> None:
        """Update the pin button to reflect whether the current deck is pinned."""
        if not ACTIVE_GUIDE_FILE.exists():
            self.sideboard_guide_panel.set_pinned(False)
            return
        try:
            import json

            with ACTIVE_GUIDE_FILE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
            current_hash = self.controller.deck_repo.get_current_decklist_hash()
            self.sideboard_guide_panel.set_pinned(data.get("deck_hash") == current_hash)
        except Exception:
            self.sideboard_guide_panel.set_pinned(False)

    def _load_guide_for_current(self: AppFrame) -> None:
        # Use decklist hash so each unique 75 has its own guide
        key = self.controller.deck_repo.get_current_decklist_hash()
        payload = self.controller.guide_store.get(key) or {}
        entries = payload.get("entries", [])

        migrated_entries = []
        for entry in entries:
            if "cards_in" in entry or "cards_out" in entry:
                play_out = self._parse_card_text(entry.get("cards_out", ""))
                play_in = self._parse_card_text(entry.get("cards_in", ""))
                migrated_entries.append(
                    {
                        "archetype": entry.get("archetype", ""),
                        "play_out": play_out,
                        "play_in": play_in,
                        "draw_out": play_out.copy(),
                        "draw_in": play_in.copy(),
                        "notes": entry.get("notes", ""),
                    }
                )
            else:
                migrated = entry.copy()
                for field in ["play_out", "play_in", "draw_out", "draw_in"]:
                    if field in migrated and isinstance(migrated[field], str):
                        migrated[field] = self._parse_card_text(migrated[field])
                migrated_entries.append(migrated)

        self.sideboard_guide_entries = migrated_entries
        self.sideboard_exclusions = payload.get("exclusions", [])
        self.sideboard_flex_slots = payload.get("flex_slots", [])
        self.sideboard_guide_panel.set_entries(
            self.sideboard_guide_entries, self.sideboard_exclusions
        )
        self._refresh_pin_indicator()

    def _persist_guide_for_current(self: AppFrame) -> None:
        key = self.controller.deck_repo.get_current_decklist_hash()
        self.controller.guide_store[key] = {
            "entries": self.sideboard_guide_entries,
            "exclusions": self.sideboard_exclusions,
            "flex_slots": self.sideboard_flex_slots,
        }
        self.controller.store_service.save_store(
            self.controller.guide_store_path, self.controller.guide_store
        )

    def _refresh_guide_view(self: AppFrame) -> None:
        self.sideboard_guide_panel.set_entries(
            self.sideboard_guide_entries, self.sideboard_exclusions
        )

    def _on_add_guide_entry(self: AppFrame) -> None:
        names = [item.get("name", "") for item in self.archetypes]
        mainboard = self.zone_cards.get("main", [])
        sideboard = self.zone_cards.get("side", [])

        dlg = GuideEntryDialog(
            self,
            names,
            mainboard_cards=mainboard,
            sideboard_cards=sideboard,
            flex_slots=self.sideboard_flex_slots,
            locale=self.locale,
        )

        while True:
            result = dlg.ShowModal()
            if result == wx.ID_CANCEL:
                break

            data = dlg.get_data()
            if data.get("archetype"):
                archetype_name = data.get("archetype")
                enable_double = data.get("enable_double_entries", False)

                entry_data = {k: v for k, v in data.items() if k != "enable_double_entries"}

                if not enable_double:
                    existing_index = None
                    for i, entry in enumerate(self.sideboard_guide_entries):
                        if entry.get("archetype") == archetype_name:
                            existing_index = i
                            break

                    if existing_index is not None:
                        self.sideboard_guide_entries[existing_index] = entry_data
                    else:
                        self.sideboard_guide_entries.append(entry_data)
                else:
                    self.sideboard_guide_entries.append(entry_data)

                self._persist_guide_for_current()
                self._refresh_guide_view()

            if result == wx.ID_OK:
                break

        dlg.Destroy()

    def _on_edit_guide_entry(self: AppFrame) -> None:
        index = self.sideboard_guide_panel.get_selected_index()
        if index is None:
            wx.MessageBox(
                "Select an entry to edit.", "Sideboard Guide", wx.OK | wx.ICON_INFORMATION
            )
            return
        data = self.sideboard_guide_entries[index]
        names = [item.get("name", "") for item in self.archetypes]
        dlg = GuideEntryDialog(
            self,
            names,
            mainboard_cards=self.zone_cards.get("main", []),
            sideboard_cards=self.zone_cards.get("side", []),
            data=data,
            flex_slots=self.sideboard_flex_slots,
            locale=self.locale,
        )
        if dlg.ShowModal() == wx.ID_OK:
            updated = dlg.get_data()
            if updated.get("archetype"):
                self.sideboard_guide_entries[index] = updated
                self._persist_guide_for_current()
                self._refresh_guide_view()
        dlg.Destroy()

    def _on_remove_guide_entry(self: AppFrame) -> None:
        index = self.sideboard_guide_panel.get_selected_index()
        if index is None:
            wx.MessageBox(
                "Select an entry to remove.", "Sideboard Guide", wx.OK | wx.ICON_INFORMATION
            )
            return
        del self.sideboard_guide_entries[index]
        self._persist_guide_for_current()
        self._refresh_guide_view()

    def _on_edit_exclusions(self: AppFrame) -> None:
        archetype_names = [item.get("name", "") for item in self.archetypes]
        dlg = wx.MultiChoiceDialog(
            self,
            "Select archetypes to exclude from the printed guide.",
            "Sideboard Guide",
            archetype_names,
        )
        selected_indices = [
            archetype_names.index(name)
            for name in self.sideboard_exclusions
            if name in archetype_names
        ]
        dlg.SetSelections(selected_indices)
        if dlg.ShowModal() == wx.ID_OK:
            selections = dlg.GetSelections()
            self.sideboard_exclusions = [archetype_names[idx] for idx in selections]
            self._persist_guide_for_current()
            self._refresh_guide_view()
        dlg.Destroy()

    def _on_edit_flex_slots(self: AppFrame) -> None:
        """Allow the user to mark which mainboard cards are flex slots."""
        mainboard_cards = self.zone_cards.get("main", [])
        if not mainboard_cards:
            wx.MessageBox("No mainboard cards loaded.", "Flex Slots", wx.OK | wx.ICON_INFORMATION)
            return

        card_names = [card["name"] for card in mainboard_cards]
        dlg = wx.MultiChoiceDialog(
            self,
            "Select mainboard cards that can be taken out during sideboarding (flex slots).\n"
            "These will be highlighted in the Out selectors when adding guide entries.",
            "Flex Slots",
            card_names,
        )
        selected_indices = [
            card_names.index(name) for name in self.sideboard_flex_slots if name in card_names
        ]
        dlg.SetSelections(selected_indices)
        if dlg.ShowModal() == wx.ID_OK:
            selections = dlg.GetSelections()
            self.sideboard_flex_slots = [card_names[idx] for idx in selections]
            self._persist_guide_for_current()
        dlg.Destroy()

    def _on_export_guide(self: AppFrame) -> None:
        """Export sideboard guide to CSV format."""
        if not self.sideboard_guide_entries:
            self._set_status("guide.status.no_entries_to_export")
            return

        dlg = wx.FileDialog(
            self,
            "Export Sideboard Guide",
            wildcard="CSV files (*.csv)|*.csv",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        )

        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return

        file_path = dlg.GetPath()
        dlg.Destroy()

        self._set_status("guide.status.exporting")

        def worker() -> None:
            try:
                self._export_guide_to_csv(file_path)
                wx.CallAfter(self._set_status, "guide.status.exported")
            except Exception as exc:
                wx.CallAfter(self._set_status, "guide.status.export_error")
                logger.exception(f"Error exporting sideboard guide to CSV: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_import_guide(self: AppFrame) -> None:
        """Import sideboard guide from CSV format."""
        self.sideboard_guide_panel.set_warning("")

        file_dlg = wx.FileDialog(
            self,
            "Import Sideboard Guide",
            wildcard="CSV files (*.csv)|*.csv",
            style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
        )

        if file_dlg.ShowModal() != wx.ID_OK:
            file_dlg.Destroy()
            return

        file_path = file_dlg.GetPath()
        file_dlg.Destroy()

        options_dlg = wx.Dialog(
            self,
            title="Import Options",
            size=(GUIDE_IMPORT_OPTIONS_DIALOG_WIDTH, GUIDE_IMPORT_OPTIONS_DIALOG_HEIGHT),
        )
        panel = wx.Panel(options_dlg)
        sizer = wx.BoxSizer(wx.VERTICAL)

        enable_double_checkbox = wx.CheckBox(panel, label="Enable double entries")
        enable_double_checkbox.SetToolTip(
            "If unchecked, will overwrite existing entries for matching archetypes. "
            "If checked, will add entries even if archetypes already exist."
        )
        sizer.Add(enable_double_checkbox, 0, wx.ALL, PADDING_XL)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer()
        ok_btn = wx.Button(panel, label="Import", id=wx.ID_OK)
        ok_btn.SetDefault()
        btn_sizer.Add(ok_btn, 0, wx.RIGHT, PADDING_BASE)
        cancel_btn = wx.Button(panel, label="Cancel", id=wx.ID_CANCEL)
        btn_sizer.Add(cancel_btn, 0)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, PADDING_BASE)

        panel.SetSizer(sizer)
        options_dlg.Centre()

        if options_dlg.ShowModal() != wx.ID_OK:
            options_dlg.Destroy()
            return

        enable_double_entries = enable_double_checkbox.GetValue()
        options_dlg.Destroy()

        self._set_status("guide.status.importing")

        def worker() -> None:
            try:
                imported_entries, warnings = self._import_guide_from_csv(file_path)
            except Exception as exc:
                wx.CallAfter(self._set_status, "guide.status.import_error")
                logger.exception(f"Error importing sideboard guide from CSV: {exc}")
                return

            def apply() -> None:
                if not imported_entries:
                    self._set_status("guide.status.no_valid_entries")
                    return

                if not enable_double_entries:
                    for imported_entry in imported_entries:
                        archetype_name = imported_entry.get("archetype")
                        existing_index = None
                        for i, entry in enumerate(self.sideboard_guide_entries):
                            if entry.get("archetype") == archetype_name:
                                existing_index = i
                                break

                        if existing_index is not None:
                            self.sideboard_guide_entries[existing_index] = imported_entry
                        else:
                            self.sideboard_guide_entries.append(imported_entry)
                else:
                    self.sideboard_guide_entries.extend(imported_entries)

                self._persist_guide_for_current()
                self._refresh_guide_view()

                if warnings:
                    warning_msg = f"Imported {len(imported_entries)} entries with warnings: {'; '.join(warnings)}"
                    self.sideboard_guide_panel.set_warning(warning_msg)
                else:
                    self._set_status("guide.status.imported", count=len(imported_entries))

            wx.CallAfter(apply)

        threading.Thread(target=worker, daemon=True).start()

    def _export_guide_to_csv(self: AppFrame, file_path: str) -> None:
        """
        Export sideboard guide to CSV with smart filtering.

        Rows are cards, columns are matchups (archetype + scenario),
        cells show actions (In/Out) and decklist is appended after a separator.
        """
        import csv

        card_actions: dict[str, dict[str, set[str]]] = {}

        for entry in self.sideboard_guide_entries:
            if entry.get("archetype") in self.sideboard_exclusions:
                continue

            archetype = entry.get("archetype", "Unknown")
            for scenario, out_key, in_key in [
                ("Play", "play_out", "play_in"),
                ("Draw", "draw_out", "draw_in"),
            ]:
                out_cards = entry.get(out_key, {})
                in_cards = entry.get(in_key, {})

                if isinstance(out_cards, dict):
                    for card_name, qty in out_cards.items():
                        if qty > 0:
                            card_actions.setdefault(card_name, {}).setdefault(
                                f"{archetype} ({scenario})", set()
                            ).add(f"Out {qty}")

                if isinstance(in_cards, dict):
                    for card_name, qty in in_cards.items():
                        if qty > 0:
                            card_actions.setdefault(card_name, {}).setdefault(
                                f"{archetype} ({scenario})", set()
                            ).add(f"In {qty}")

        filtered_cards = {card: actions for card, actions in card_actions.items() if actions}
        if not filtered_cards:
            raise ValueError("No cards to export after filtering")

        all_matchups = sorted(
            {matchup for actions in filtered_cards.values() for matchup in actions.keys()}
        )

        with open(file_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["Card"] + all_matchups)

            for card_name in sorted(filtered_cards.keys()):
                row = [card_name]
                for matchup in all_matchups:
                    actions = filtered_cards[card_name].get(matchup, set())
                    row.append(" & ".join(sorted(actions)) if actions else "")
                writer.writerow(row)

            writer.writerow([])
            writer.writerow([])
            writer.writerow(["DECKLIST"])
            writer.writerow([])

            writer.writerow(["Mainboard"])
            mainboard_cards = self.zone_cards.get("main", [])
            for card in sorted(mainboard_cards, key=lambda c: c.get("name", "")):
                writer.writerow([f"{card.get('qty', 0)} {card.get('name', '')}"])

            writer.writerow([])
            writer.writerow(["Sideboard"])
            sideboard_cards = self.zone_cards.get("side", [])
            for card in sorted(sideboard_cards, key=lambda c: c.get("name", "")):
                writer.writerow([f"{card.get('qty', 0)} {card.get('name', '')}"])

    def _import_guide_from_csv(
        self: AppFrame, file_path: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """
        Import sideboard guide from CSV format with sanitization.

        Returns imported entries and list of warning messages.
        """
        import csv
        import re

        mainboard_names = {card["name"] for card in self.zone_cards.get("main", [])}
        sideboard_names = {card["name"] for card in self.zone_cards.get("side", [])}

        entries_by_archetype: dict[str, dict[str, dict[str, int]]] = {}
        warnings: list[str] = []
        missing_cards: set[str] = set()

        with open(file_path, encoding="utf-8") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header or header[0] != "Card":
                raise ValueError("Invalid CSV format: expected 'Card' as first column header")

            matchup_columns = header[1:]
            archetype_scenario_map: list[tuple[str | None, str | None]] = []
            for col in matchup_columns:
                match = re.match(r"^(.+?)\s*\((Play|Draw)\)$", col)
                if match:
                    archetype_name = match.group(1).strip()
                    scenario = match.group(2).lower()
                    archetype_scenario_map.append((archetype_name, scenario))
                else:
                    archetype_scenario_map.append((None, None))

            for row in reader:
                if not row:
                    continue
                if row[0] in ["DECKLIST", "Mainboard", "Sideboard"]:
                    break

                card_name = row[0].strip()
                if not card_name:
                    continue

                for idx, cell_value in enumerate(row[1:], start=0):
                    if idx >= len(archetype_scenario_map):
                        continue
                    archetype_name, scenario = archetype_scenario_map[idx]
                    if not archetype_name or not scenario:
                        continue
                    if not cell_value or not cell_value.strip():
                        continue

                    entries_by_archetype.setdefault(
                        archetype_name,
                        {"play_out": {}, "play_in": {}, "draw_out": {}, "draw_in": {}},
                    )

                    actions = cell_value.split("&")
                    for action in actions:
                        action = action.strip()
                        match = re.match(r"^(Out|In)\s+(\d+)$", action)
                        if not match:
                            continue
                        direction = match.group(1).lower()
                        qty = int(match.group(2))
                        key = f"{scenario}_{direction}"

                        if direction == "out" and card_name not in mainboard_names:
                            missing_cards.add(f"{card_name} (not in mainboard)")
                            continue
                        if direction == "in" and card_name not in sideboard_names:
                            missing_cards.add(f"{card_name} (not in sideboard)")
                            continue

                        entries_by_archetype[archetype_name][key][card_name] = qty

        imported_entries = [
            {
                "archetype": archetype_name,
                "play_out": data["play_out"],
                "play_in": data["play_in"],
                "draw_out": data["draw_out"],
                "draw_in": data["draw_in"],
                "notes": "",
            }
            for archetype_name, data in entries_by_archetype.items()
        ]

        if missing_cards:
            warnings.append(f"Cards not in deck: {', '.join(sorted(missing_cards))}")

        return imported_entries, warnings

    def _on_pin_guide(self: AppFrame) -> None:
        """Pin the current deck's sideboard guide for use in the Opponent Tracker."""
        deck_hash = self.controller.deck_repo.get_current_decklist_hash()
        current_deck = self.controller.deck_repo.get_current_deck()
        deck_name = ""
        if current_deck:
            deck_name = current_deck.get("name") or current_deck.get("archetype") or ""

        payload = {"deck_hash": deck_hash, "deck_name": deck_name}
        try:
            atomic_write_json(ACTIVE_GUIDE_FILE, payload, indent=2)
            self.sideboard_guide_panel.set_pinned(True)
            self._set_status(
                "guide.status.pinned", name=deck_name or deck_hash[:DECK_HASH_DISPLAY_LENGTH]
            )
            logger.info(f"Pinned guide: hash={deck_hash}, name={deck_name!r}")
        except OSError as exc:
            logger.error(f"Failed to save active guide: {exc}")
            self._set_status("guide.status.pin_error")

    def _parse_card_text(self: AppFrame, text: str) -> dict[str, int]:
        """Parse text like '2x Lightning Bolt, 1x Mountain' into a dict."""
        if not text or not isinstance(text, str):
            return {}

        result: dict[str, int] = {}
        lines = text.replace(",", "\n").split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                qty_str, name = parts
                qty_str = qty_str.rstrip("x")
                try:
                    qty = int(qty_str)
                    result[name.strip()] = qty
                    continue
                except ValueError:
                    pass
            result[line] = 1
        return result
