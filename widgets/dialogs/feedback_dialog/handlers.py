"""Export worker handlers for the feedback dialog."""

from __future__ import annotations

import threading
from pathlib import Path

import wx
from loguru import logger

from utils.diagnostics import export_diagnostics_bundle


class FeedbackDialogHandlersMixin:
    """Diagnostics export handlers for :class:`FeedbackDialog`."""

    _logs_dir: Path
    _notes_ctrl: wx.TextCtrl
    _include_events_check: wx.CheckBox
    _export_btn: wx.Button
    _status_label: wx.StaticText

    def _on_export(self, _evt: wx.CommandEvent) -> None:
        default_name = f"mtgo_tools_diagnostics_{_timestamp()}.zip"
        with wx.FileDialog(
            self,
            "Save diagnostics bundle",
            defaultFile=default_name,
            wildcard="ZIP files (*.zip)|*.zip",
            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
        ) as dlg:
            if dlg.ShowModal() != wx.ID_OK:
                return
            dest = Path(dlg.GetPath())

        notes = self._notes_ctrl.GetValue()
        include_events = self._include_events_check.GetValue()

        self._export_btn.Disable()
        self._status_label.SetLabel("Exporting…")

        def _worker() -> None:
            try:
                out = export_diagnostics_bundle(
                    dest,
                    logs_dir=self._logs_dir,
                    notes=notes,
                    include_events=include_events,
                )
                wx.CallAfter(self._on_export_done, out, None)
            except Exception as exc:
                logger.exception("Failed to export diagnostics bundle")
                wx.CallAfter(self._on_export_done, None, exc)

        threading.Thread(target=_worker, daemon=True).start()

    def _on_export_done(self, out: Path | None, exc: Exception | None) -> None:
        self._status_label.SetLabel("")
        self._export_btn.Enable()
        if exc is not None:
            wx.MessageBox(
                f"Export failed: {exc}",
                "Export Error",
                wx.OK | wx.ICON_ERROR,
            )
        else:
            wx.MessageBox(
                f"Diagnostics bundle saved to:\n{out}",
                "Export complete",
                wx.OK | wx.ICON_INFORMATION,
            )


def _timestamp() -> str:
    from datetime import datetime

    return datetime.now().strftime("%Y%m%d_%H%M%S")
