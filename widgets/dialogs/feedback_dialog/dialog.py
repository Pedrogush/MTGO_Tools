"""Dialog for collecting user notes and exporting a diagnostics bundle."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import wx

from utils.constants import DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from widgets.dialogs.feedback_dialog.handlers import FeedbackDialogHandlersMixin
from widgets.dialogs.feedback_dialog.properties import FeedbackDialogPropertiesMixin


class FeedbackDialog(FeedbackDialogHandlersMixin, FeedbackDialogPropertiesMixin, wx.Dialog):
    """Let users add optional notes and export a local diagnostics zip.

    No data is uploaded anywhere.  The exported zip can be shared manually.
    """

    def __init__(
        self,
        parent: wx.Window,
        logs_dir: Path,
        *,
        event_logging_enabled: bool = False,
    ) -> None:
        super().__init__(parent, title="Export Diagnostics / Send Feedback", size=(480, 380))
        self.SetBackgroundColour(DARK_BG)

        self._logs_dir = logs_dir
        self._event_logging_enabled = event_logging_enabled

        self._build_ui()
        self.Centre()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Heading
        title = wx.StaticText(panel, label="Export Diagnostics")
        title.SetForegroundColour(LIGHT_TEXT)
        font = title.GetFont()
        font.PointSize += 2
        title.SetFont(font.Bold())
        sizer.Add(title, 0, wx.ALL, 10)

        # Description
        desc = wx.StaticText(
            panel,
            label=(
                "Creates a local .zip file containing log files and system info.\n"
                "No data is uploaded – you share the file manually."
            ),
        )
        desc.SetForegroundColour(SUBDUED_TEXT)
        desc.Wrap(440)
        sizer.Add(desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Notes area
        notes_label = wx.StaticText(panel, label="Notes (optional):")
        notes_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(notes_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

        self._notes_ctrl = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_WORDWRAP,
            size=(-1, 80),
        )
        self._notes_ctrl.SetBackgroundColour(DARK_PANEL)
        self._notes_ctrl.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self._notes_ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Opt-in event logging checkbox
        self._event_log_check = wx.CheckBox(
            panel, label="Enable opt-in event logging (stored locally only)"
        )
        self._event_log_check.SetForegroundColour(LIGHT_TEXT)
        self._event_log_check.SetValue(self._event_logging_enabled)
        sizer.Add(self._event_log_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        event_log_desc = wx.StaticText(
            panel,
            label="When enabled, feature usage events are saved locally to logs/events.jsonl.",
        )
        event_log_desc.SetForegroundColour(SUBDUED_TEXT)
        event_log_desc.Wrap(440)
        sizer.Add(event_log_desc, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Include events in export checkbox
        self._include_events_check = wx.CheckBox(panel, label="Include event log in export")
        self._include_events_check.SetForegroundColour(LIGHT_TEXT)
        self._include_events_check.SetValue(True)
        sizer.Add(self._include_events_check, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Status label (shown during export)
        self._status_label = wx.StaticText(panel, label="")
        self._status_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self._status_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        # Buttons
        sizer.AddStretchSpacer(1)
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        btn_sizer.AddStretchSpacer(1)

        close_btn = wx.Button(panel, wx.ID_CANCEL, label="Close")
        btn_sizer.Add(close_btn, 0, wx.RIGHT, 6)

        self._export_btn = wx.Button(panel, wx.ID_OK, label="Export to File…")
        self._export_btn.SetDefault()
        self._export_btn.Bind(wx.EVT_BUTTON, self._on_export)
        btn_sizer.Add(self._export_btn, 0)

        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)

        panel.SetSizer(sizer)


def show_feedback_dialog(
    parent: wx.Window,
    logs_dir: Path,
    *,
    event_logging_enabled: bool = False,
    on_event_logging_changed: Callable[[bool], None] | None = None,
) -> None:
    """Open the feedback/diagnostics dialog and apply any setting changes."""
    dlg = FeedbackDialog(parent, logs_dir, event_logging_enabled=event_logging_enabled)
    dlg.ShowModal()

    if on_event_logging_changed is not None:
        on_event_logging_changed(dlg.event_logging_enabled)

    dlg.Destroy()
