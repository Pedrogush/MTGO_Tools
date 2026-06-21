"""CSV import/export handlers for the sideboard guide."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants.ui_layout import PADDING_BASE, PADDING_XL
from utils.constants.ui_windows import (
    GUIDE_IMPORT_OPTIONS_DIALOG_HEIGHT,
    GUIDE_IMPORT_OPTIONS_DIALOG_WIDTH,
)
from widgets.frames.app_frame.handlers.sideboard_guide_csv import (
    export_guide_to_csv,
    import_guide_from_csv,
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
                export_guide_to_csv(
                    self.sideboard_guide_entries,
                    self.sideboard_exclusions,
                    self.zone_cards,
                    file_path,
                )
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
                mainboard_names = {card["name"] for card in self.zone_cards.get("main", [])}
                sideboard_names = {card["name"] for card in self.zone_cards.get("side", [])}
                imported_entries, warnings = import_guide_from_csv(
                    file_path, mainboard_names, sideboard_names
                )
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
