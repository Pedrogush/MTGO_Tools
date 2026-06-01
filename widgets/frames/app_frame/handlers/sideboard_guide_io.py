"""CSV import/export handlers for the sideboard guide."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.constants.ui_layout import PADDING_BASE, PADDING_XL
from utils.constants.ui_windows import (
    GUIDE_IMPORT_OPTIONS_DIALOG_HEIGHT,
    GUIDE_IMPORT_OPTIONS_DIALOG_WIDTH,
)

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class SideboardGuideImportExportHandlers(_Base):
    """CSV import/export, matchup parsing, and threaded I/O workers."""

    def _on_export_guide(self: AppFrame) -> None:
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

    def _parse_card_text(self: AppFrame, text: str) -> dict[str, int]:
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
