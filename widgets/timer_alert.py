"""wxPython variant of the MTGO challenge timer alert widget."""

from __future__ import annotations

import re
import threading
from typing import Any

import wx
from loguru import logger

from utils import mtgo_bridge
from utils.constants import (
    DARK_ACCENT,
    DARK_ALT,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    PADDING_BASE,
    PADDING_LG,
    PADDING_MD,
    PADDING_SM,
    PADDING_XL,
    SUBDUED_TEXT,
    TIMER_ALERT_CHALLENGE_WRAP_WIDTH,
    TIMER_ALERT_DEFAULT_THRESHOLD_VALUE,
    TIMER_ALERT_FRAME_SIZE,
    TIMER_ALERT_POLL_INTERVAL_MAX_MS,
    TIMER_ALERT_POLL_INTERVAL_MIN_MS,
    TIMER_ALERT_POLL_INTERVAL_MS,
    TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_MS,
    TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_SECONDS,
    TIMER_ALERT_REPEAT_INTERVAL_MAX_SECONDS,
    TIMER_ALERT_REPEAT_INTERVAL_MIN_SECONDS,
    TIMER_ALERT_REMOVE_BUTTON_SIZE,
    TIMER_ALERT_SCROLL_RATE_Y,
    TIMER_ALERT_STATUS_MIN_HEIGHT,
    TIMER_ALERT_THRESHOLD_INPUT_SIZE,
    TIMER_ALERT_WATCH_INTERVAL_MS,
)
from utils.mtgo_bridge_client import BridgeWatcher

try:
    import winsound  # type: ignore[attr-defined]

    SOUND_AVAILABLE = True
except Exception:  # pragma: no cover - fallback for non-Windows environments
    SOUND_AVAILABLE = False
    logger.warning("winsound not available, alarm sounds will not play")

# Built-in Windows sounds (always available)
SOUND_OPTIONS = {
    "Beep": "SystemAsterisk",
    "Alert": "SystemExclamation",
    "Warning": "SystemHand",
    "Question": "SystemQuestion",
    "Default": "SystemDefault",
}


class ThresholdPanel(wx.Panel):
    """Individual threshold entry with MM:SS format."""

    def __init__(self, parent: wx.Window, on_remove: callable = None) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(DARK_BG)
        self.on_remove_callback = on_remove

        sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(sizer)

        # MM:SS input
        self.time_input = wx.TextCtrl(self, size=TIMER_ALERT_THRESHOLD_INPUT_SIZE, value=TIMER_ALERT_DEFAULT_THRESHOLD_VALUE)
        self._stylize_entry(self.time_input)
        sizer.Add(self.time_input, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_BASE)

        # Remove button
        self.remove_btn = wx.Button(self, label="✕", size=TIMER_ALERT_REMOVE_BUTTON_SIZE)
        self._stylize_remove_button(self.remove_btn)
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove)
        sizer.Add(self.remove_btn, 0, wx.ALIGN_CENTER_VERTICAL)

    def _stylize_entry(self, entry: wx.TextCtrl) -> None:
        entry.SetBackgroundColour(DARK_ALT)
        entry.SetForegroundColour(LIGHT_TEXT)

    def _stylize_remove_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(wx.Colour(139, 35, 35))
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _on_remove(self, _event: wx.CommandEvent) -> None:
        if self.on_remove_callback:
            self.on_remove_callback(self)

    def get_seconds(self) -> int | None:
        """Parse MM:SS format to seconds."""
        value = self.time_input.GetValue().strip()
        match = re.match(r"^(\d+):(\d{2})$", value)
        if not match:
            return None
        minutes, seconds = match.groups()
        return int(minutes) * 60 + int(seconds)

    def set_enabled(self, enabled: bool) -> None:
        """Enable/disable the input."""
        self.time_input.Enable(enabled)
        self.remove_btn.Enable(enabled)


class TimerAlertFrame(wx.Frame):
    """Polls MTGO challenge timers via the bridge and plays audible alerts."""

    WATCH_INTERVAL_MS = TIMER_ALERT_WATCH_INTERVAL_MS
    POLL_INTERVAL_MS = TIMER_ALERT_POLL_INTERVAL_MS

    def __init__(self, parent: wx.Window | None = None) -> None:
        style = wx.CAPTION | wx.CLOSE_BOX | wx.MINIMIZE_BOX | wx.STAY_ON_TOP | wx.RESIZE_BORDER
        super().__init__(parent, title="MTGO Timer Alert", size=TIMER_ALERT_FRAME_SIZE, style=style)

        self._watcher: BridgeWatcher | None = None
        self._watch_timer = wx.Timer(self)
        self._monitor_timer = wx.Timer(self)
        self._repeat_timer = wx.Timer(self)

        self._last_snapshot: dict[str, Any] | None = None
        self.challenge_text: wx.StaticText | None = None
        self.threshold_panels: list[ThresholdPanel] = []

        self.monitor_job_active = False
        self.triggered_thresholds: set[int] = set()
        self.start_alert_sent = False
        self._current_thresholds: list[int] = []
        self._monitor_interval_ms = TIMER_ALERT_POLL_INTERVAL_MS
        self._repeat_interval_ms = TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_MS

        self._build_ui()

        self.Bind(wx.EVT_TIMER, self._on_watch_timer, self._watch_timer)
        self.Bind(wx.EVT_TIMER, self._on_monitor_timer, self._monitor_timer)
        self.Bind(wx.EVT_TIMER, self._on_repeat_timer, self._repeat_timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        wx.CallAfter(self._start_watch_loop)

    # ------------------------------------------------------------------ UI ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        # Thresholds section
        threshold_box = wx.StaticBox(panel, label="Alert Thresholds")
        threshold_box.SetForegroundColour(LIGHT_TEXT)
        threshold_box.SetBackgroundColour(DARK_PANEL)
        threshold_sizer = wx.StaticBoxSizer(threshold_box, wx.VERTICAL)
        box_parent = threshold_sizer.GetStaticBox()

        instructions = wx.StaticText(
            box_parent, label="Enter time in MM:SS format (e.g., 05:00 for 5 minutes)"
        )
        instructions.SetForegroundColour(SUBDUED_TEXT)
        threshold_sizer.Add(instructions, 0, wx.ALL, PADDING_SM)

        # Scrollable threshold container
        self.threshold_container = wx.ScrolledWindow(box_parent, style=wx.VSCROLL)
        self.threshold_container.SetBackgroundColour(DARK_BG)
        self.threshold_container.SetScrollRate(0, TIMER_ALERT_SCROLL_RATE_Y)
        self.threshold_container_sizer = wx.BoxSizer(wx.VERTICAL)
        self.threshold_container.SetSizer(self.threshold_container_sizer)
        threshold_sizer.Add(self.threshold_container, 1, wx.EXPAND | wx.ALL, PADDING_SM)

        # Add initial threshold
        self._add_threshold_panel()

        # Add threshold button
        add_btn = wx.Button(box_parent, label="+ Add Another Threshold")
        self._stylize_secondary_button(add_btn)
        add_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._add_threshold_panel())
        threshold_sizer.Add(add_btn, 0, wx.ALL, PADDING_SM)

        sizer.Add(threshold_sizer, 1, wx.ALL | wx.EXPAND, PADDING_XL)

        # Options section
        options_grid = wx.FlexGridSizer(cols=2, hgap=PADDING_BASE, vgap=PADDING_BASE)
        options_grid.AddGrowableCol(1, 1)

        # Sound selection
        options_grid.Add(self._static_text(panel, "Alert Sound:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.sound_choice = wx.Choice(panel, choices=list(SOUND_OPTIONS.keys()))
        self._stylize_choice(self.sound_choice)
        self.sound_choice.SetSelection(0)
        options_grid.Add(self.sound_choice, 0, wx.EXPAND)

        # Poll interval
        options_grid.Add(
            self._static_text(panel, "Check interval (ms):"), 0, wx.ALIGN_CENTER_VERTICAL
        )
        self.poll_interval_ctrl = wx.SpinCtrl(
            panel,
            min=TIMER_ALERT_POLL_INTERVAL_MIN_MS,
            max=TIMER_ALERT_POLL_INTERVAL_MAX_MS,
            initial=TIMER_ALERT_POLL_INTERVAL_MS,
        )
        self._stylize_spin(self.poll_interval_ctrl)
        options_grid.Add(self.poll_interval_ctrl, 0, wx.EXPAND)

        # Repeat interval
        options_grid.Add(
            self._static_text(panel, "Repeat interval (seconds):"), 0, wx.ALIGN_CENTER_VERTICAL
        )
        self.repeat_interval_ctrl = wx.SpinCtrl(
            panel,
            min=TIMER_ALERT_REPEAT_INTERVAL_MIN_SECONDS,
            max=TIMER_ALERT_REPEAT_INTERVAL_MAX_SECONDS,
            initial=TIMER_ALERT_REPEAT_INTERVAL_DEFAULT_SECONDS,
        )
        self._stylize_spin(self.repeat_interval_ctrl)
        options_grid.Add(self.repeat_interval_ctrl, 0, wx.EXPAND)

        sizer.Add(options_grid, 0, wx.LEFT | wx.RIGHT | wx.EXPAND, PADDING_XL)

        # Checkboxes
        self.start_alert_checkbox = wx.CheckBox(
            panel, label="Alert when timer starts counting down"
        )
        self.start_alert_checkbox.SetValue(True)
        self.start_alert_checkbox.SetForegroundColour(LIGHT_TEXT)
        self.start_alert_checkbox.SetBackgroundColour(DARK_BG)
        sizer.Add(self.start_alert_checkbox, 0, wx.LEFT | wx.RIGHT | wx.TOP, PADDING_XL)

        self.repeat_alarm_checkbox = wx.CheckBox(panel, label="Repeat alarm at interval")
        self.repeat_alarm_checkbox.SetValue(False)
        self.repeat_alarm_checkbox.SetForegroundColour(LIGHT_TEXT)
        self.repeat_alarm_checkbox.SetBackgroundColour(DARK_BG)
        sizer.Add(self.repeat_alarm_checkbox, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_XL)

        # Control buttons
        button_row = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(button_row, 0, wx.ALL | wx.EXPAND, PADDING_XL)

        start_btn = wx.Button(panel, label="Start Monitoring")
        self._stylize_primary_button(start_btn)
        start_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.start_monitoring())
        button_row.Add(start_btn, 0, wx.RIGHT, PADDING_MD)

        stop_btn = wx.Button(panel, label="Stop")
        self._stylize_secondary_button(stop_btn)
        stop_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.stop_monitoring())
        button_row.Add(stop_btn, 0, wx.RIGHT, PADDING_MD)

        test_btn = wx.Button(panel, label="Test Alert")
        self._stylize_secondary_button(test_btn)
        test_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.test_alert())
        button_row.Add(test_btn, 0)

        # Status display
        self.status_text = wx.TextCtrl(
            panel,
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_WORDWRAP | wx.BORDER_NONE,
        )
        self.status_text.SetMinSize((-1, TIMER_ALERT_STATUS_MIN_HEIGHT))
        self.status_text.SetBackgroundColour(DARK_ALT)
        self.status_text.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.status_text, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, PADDING_XL)

        # Challenge timer display
        challenge_box = wx.StaticBox(panel, label="Active Challenge Timer")
        challenge_box.SetForegroundColour(LIGHT_TEXT)
        challenge_box.SetBackgroundColour(DARK_PANEL)
        challenge_sizer = wx.StaticBoxSizer(challenge_box, wx.VERTICAL)
        self.challenge_text = wx.StaticText(
            challenge_box, label="No active challenge timer detected."
        )
        self.challenge_text.SetForegroundColour(LIGHT_TEXT)
        self.challenge_text.SetBackgroundColour(DARK_PANEL)
        self.challenge_text.Wrap(TIMER_ALERT_CHALLENGE_WRAP_WIDTH)
        challenge_sizer.Add(self.challenge_text, 0, wx.ALL | wx.EXPAND, PADDING_BASE)
        sizer.Add(challenge_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, PADDING_XL)

        self._set_status("Configure thresholds and click Start to begin monitoring.")
        self.Bind(wx.EVT_SIZE, self._on_resize)

    def _add_threshold_panel(self) -> None:
        """Add a new threshold input panel."""
        panel = ThresholdPanel(self.threshold_container, on_remove=self._remove_threshold_panel)
        self.threshold_panels.append(panel)
        self.threshold_container_sizer.Add(panel, 0, wx.EXPAND | wx.BOTTOM, PADDING_SM)
        self.threshold_container.Layout()
        self.threshold_container.FitInside()

    def _remove_threshold_panel(self, panel: ThresholdPanel) -> None:
        """Remove a threshold input panel."""
        if len(self.threshold_panels) <= 1:
            self._set_status("At least one timer threshold is required.")
            return
        self.threshold_panels.remove(panel)
        self.threshold_container_sizer.Detach(panel)
        panel.Destroy()
        self.threshold_container.Layout()
        self.threshold_container.FitInside()

    def _static_text(self, parent: wx.Window, label: str) -> wx.StaticText:
        text = wx.StaticText(parent, label=label)
        text.SetForegroundColour(LIGHT_TEXT)
        text.SetBackgroundColour(DARK_BG)
        return text

    def _stylize_choice(self, choice: wx.Choice) -> None:
        choice.SetBackgroundColour(DARK_ALT)
        choice.SetForegroundColour(LIGHT_TEXT)

    def _stylize_spin(self, ctrl: wx.SpinCtrl) -> None:
        ctrl.SetBackgroundColour(DARK_ALT)
        ctrl.SetForegroundColour(LIGHT_TEXT)

    def _stylize_primary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_ACCENT)
        button.SetForegroundColour(wx.Colour(12, 14, 18))
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _stylize_secondary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    # ------------------------------------------------------------------ Monitoring ------------------------------------------------------------
    def start_monitoring(self) -> None:
        if self.monitor_job_active:
            self._set_status("Already monitoring the timer.")
            return

        thresholds = self._parse_thresholds()
        if not thresholds:
            self._set_status("No valid thresholds configured.")
            return

        try:
            poll_interval = max(250, int(self.poll_interval_ctrl.GetValue()))
        except (TypeError, ValueError):
            self._set_status("Invalid poll interval.")
            return

        self._current_thresholds = thresholds
        self._monitor_interval_ms = poll_interval
        self._repeat_interval_ms = self.repeat_interval_ctrl.GetValue() * 1000
        self.triggered_thresholds.clear()
        self.start_alert_sent = False
        self.monitor_job_active = True

        # Disable threshold editing
        for panel in self.threshold_panels:
            panel.set_enabled(False)

        self._monitor_timer.Start(self._monitor_interval_ms)
        self._set_status("Monitoring MTGO challenge timer…")
        self._monitor_timer_step()

    def stop_monitoring(self) -> None:
        if self._monitor_timer.IsRunning():
            self._monitor_timer.Stop()
        if self._repeat_timer.IsRunning():
            self._repeat_timer.Stop()
        self.monitor_job_active = False

        # Re-enable threshold editing
        for panel in self.threshold_panels:
            panel.set_enabled(True)

        self._set_status("Monitoring stopped.")

    def test_alert(self) -> None:
        """Test the selected alert sound."""
        self._play_alert()

    def _parse_thresholds(self) -> list[int]:
        """Parse all threshold panels and return valid seconds."""
        thresholds: list[int] = []
        for panel in self.threshold_panels:
            seconds = panel.get_seconds()
            if seconds is not None and seconds > 0:
                thresholds.append(seconds)
            elif panel.time_input.GetValue().strip():
                logger.warning(f"Invalid threshold format: {panel.time_input.GetValue()}")
        thresholds.sort(reverse=True)
        return thresholds

    def _monitor_timer_step(self) -> None:
        snapshot = self._last_snapshot
        if snapshot is None:
            self._set_status("Waiting for MTGO data…")
            return

        if snapshot.get("error"):
            self._set_status(f"Bridge error: {snapshot['error']}")
            return

        self._update_challenge_display(snapshot)

        # Get challenge timer info
        timers = snapshot.get("challengeTimers") or []
        if not timers:
            self._set_status("No active challenge timer detected. Join an event to monitor.")
            self.triggered_thresholds.clear()
            self.start_alert_sent = False
            if self._repeat_timer.IsRunning():
                self._repeat_timer.Stop()
            return

        timer = timers[0]
        remaining = timer.get("remainingSeconds")
        if not isinstance(remaining, (int, float)):
            self._set_status("Unable to read challenge timer value.")
            return

        current_seconds = max(0, int(remaining))
        self._set_status(f"Challenge timer: {self._format_seconds(current_seconds)}")

        # Start alert (countdown began)
        if self.start_alert_checkbox.GetValue() and not self.start_alert_sent:
            self._trigger_alert("Countdown started")
            self.start_alert_sent = True
            if self.repeat_alarm_checkbox.GetValue():
                self._repeat_timer.Start(self._repeat_interval_ms)

        # Threshold alerts
        for threshold in self._current_thresholds:
            if threshold < 0 or threshold in self.triggered_thresholds:
                continue
            if current_seconds <= threshold:
                self._trigger_alert(f"Timer reached {self._format_seconds(threshold)}")
                self.triggered_thresholds.add(threshold)

    def _trigger_alert(self, message: str) -> None:
        """Play the alert sound."""
        logger.debug(f"Timer alert: {message}")
        self._play_alert()

    def _play_alert(self) -> None:
        """Play the selected system sound."""
        if not SOUND_AVAILABLE:
            logger.warning("Sound playback not available")
            return

        sound_name = self.sound_choice.GetStringSelection()
        sound_key = SOUND_OPTIONS.get(sound_name, "SystemDefault")

        try:
            winsound.PlaySound(sound_key, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to play sound: {exc}")

    def _on_repeat_timer(self, _event: wx.TimerEvent) -> None:
        """Repeat alarm timer fired."""
        if self.monitor_job_active and self.repeat_alarm_checkbox.GetValue():
            self._play_alert()

    def _format_seconds(self, value: Any) -> str:
        if not isinstance(value, (int, float)):
            return "—"
        total = max(0, int(round(value)))
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    # ------------------------------------------------------------------ Watch loop -----------------------------------------------------------
    def _start_watch_loop(self) -> None:
        if self._watcher:
            return

        def starter():
            try:
                watcher = mtgo_bridge.start_watch(interval_ms=self.WATCH_INTERVAL_MS)
            except FileNotFoundError as exc:
                wx.CallAfter(
                    self._set_status,
                    "Bridge missing. Build the MTGO bridge executable.",
                )
                logger.error("Bridge executable not found: %s", exc)
                wx.CallLater(5000, self._start_watch_loop)
                return
            except Exception as exc:  # noqa: BLE001
                logger.exception("Unable to start bridge watcher")
                wx.CallAfter(self._set_status, f"Bridge error: {exc}")
                wx.CallLater(5000, self._start_watch_loop)
                return
            self._watcher = watcher
            wx.CallAfter(self._watch_timer.Start, self.WATCH_INTERVAL_MS)

        threading.Thread(target=starter, daemon=True).start()

    def _on_watch_timer(self, _event: wx.TimerEvent) -> None:
        if not self._watcher:
            return
        payload = self._watcher.latest()
        if not payload:
            return
        self._last_snapshot = payload
        self._update_challenge_display(payload)

    def _on_monitor_timer(self, _event: wx.TimerEvent) -> None:
        self._monitor_timer_step()

    # ------------------------------------------------------------------ Helpers --------------------------------------------------------------
    def _set_status(self, message: str) -> None:
        self.status_text.ChangeValue(message)

    def _update_challenge_display(self, snapshot: dict[str, Any]) -> None:
        if not self.challenge_text:
            return
        timers = snapshot.get("challengeTimers") or []
        if not timers:
            self.challenge_text.SetLabel("No active challenge timer detected.")
            self.challenge_text.Wrap(self._challenge_wrap_width())
            return
        lines: list[str] = []
        for timer in timers:
            desc = timer.get("description") or timer.get("eventId") or "Challenge"
            state = timer.get("state") or "Unknown"
            remaining = timer.get("remainingSeconds")
            remaining_display = self._format_seconds(remaining)
            fmt = timer.get("format")
            line = desc
            if fmt and fmt.lower() != "no format found":
                line += f" • {fmt}"
            line += f" ({state}) — {remaining_display}"
            lines.append(line)
        self.challenge_text.SetLabel("\n".join(lines))
        self.challenge_text.Wrap(self._challenge_wrap_width())

    def _challenge_wrap_width(self) -> int:
        if not self.challenge_text:
            return 340
        parent = self.challenge_text.GetParent()
        width = parent.GetClientSize().width if parent else 0
        return max(240, width - 24)

    def _on_resize(self, event: wx.Event) -> None:
        if self.challenge_text:
            self.challenge_text.Wrap(self._challenge_wrap_width())
        event.Skip()

    # ------------------------------------------------------------------ Lifecycle -------------------------------------------------------------
    def on_close(self, event: wx.CloseEvent) -> None:
        if self._watch_timer.IsRunning():
            self._watch_timer.Stop()
        if self._monitor_timer.IsRunning():
            self._monitor_timer.Stop()
        if self._repeat_timer.IsRunning():
            self._repeat_timer.Stop()
        if self._watcher:
            try:
                self._watcher.stop()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Failed to stop bridge watcher: {exc}")
            self._watcher = None
        event.Skip()


__all__ = ["TimerAlertFrame"]
