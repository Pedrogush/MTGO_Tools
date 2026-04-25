"""Event handlers, monitoring, and bridge-watch callbacks for the timer alert widget.

The ``mtgo_bridge``, ``wx``, and ``threading`` module-level references here are
the ones used at runtime; tests that do
``monkeypatch.setattr(timer_alert.<module>, name, ...)`` patch attributes on
the module object itself, which is shared with this module's imports.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils import mtgo_bridge
from utils.mtgo_bridge_client import BridgeWatcher

if TYPE_CHECKING:
    from widgets.frames.timer_alert.frame import ThresholdPanel

try:
    import winsound  # type: ignore[attr-defined]

    _SOUND_AVAILABLE = True
except Exception:  # pragma: no cover - fallback for non-Windows environments
    _SOUND_AVAILABLE = False

# Built-in Windows sounds (always available); kept in sync with frame.py.
_SOUND_OPTIONS = {
    "Beep": "SystemAsterisk",
    "Alert": "SystemExclamation",
    "Warning": "SystemHand",
    "Question": "SystemQuestion",
    "Default": "SystemDefault",
}


class TimerAlertHandlersMixin:
    """Timer and monitor callbacks, bridge watcher lifecycle, alert playback."""

    WATCH_INTERVAL_MS: int
    WATCH_RETRY_DELAY_MS: int
    POLL_INTERVAL_MS: int

    _watcher: BridgeWatcher | None
    _watch_start_pending: bool
    _closed: bool
    _watch_timer: wx.Timer
    _monitor_timer: wx.Timer
    _repeat_timer: wx.Timer
    _last_snapshot: dict[str, Any] | None
    _current_thresholds: list[int]
    _monitor_interval_ms: int
    _repeat_interval_ms: int
    triggered_thresholds: set[int]
    start_alert_sent: bool
    monitor_job_active: bool
    threshold_panels: list[ThresholdPanel]
    sound_choice: wx.Choice
    poll_interval_ctrl: wx.SpinCtrl
    repeat_interval_ctrl: wx.SpinCtrl
    start_alert_checkbox: wx.CheckBox
    repeat_alarm_checkbox: wx.CheckBox

    # ------------------------------------------------------------------ monitoring
    def start_monitoring(self) -> None:
        if self.monitor_job_active:
            self._set_status("timer.status.already_monitoring")
            return

        thresholds = self._parse_thresholds()
        if not thresholds:
            self._set_status("timer.status.no_thresholds")
            return

        try:
            poll_interval = max(250, int(self.poll_interval_ctrl.GetValue()))
        except (TypeError, ValueError):
            self._set_status("timer.status.invalid_poll_interval")
            return

        self._current_thresholds = thresholds
        self._monitor_interval_ms = poll_interval
        self._repeat_interval_ms = self.repeat_interval_ctrl.GetValue() * 1000
        self.triggered_thresholds.clear()
        self.start_alert_sent = False
        self.monitor_job_active = True

        for panel in self.threshold_panels:
            panel.set_enabled(False)

        self._monitor_timer.Start(self._monitor_interval_ms)
        self._set_status("timer.status.monitoring")
        self._monitor_timer_step()

    def stop_monitoring(self) -> None:
        if self._monitor_timer.IsRunning():
            self._monitor_timer.Stop()
        if self._repeat_timer.IsRunning():
            self._repeat_timer.Stop()
        self.monitor_job_active = False

        for panel in self.threshold_panels:
            panel.set_enabled(True)

        self._set_status("timer.status.stopped")

    def test_alert(self) -> None:
        self._play_alert()

    def _monitor_timer_step(self) -> None:
        snapshot = self._last_snapshot
        if snapshot is None:
            self._set_status("timer.status.waiting_data")
            return

        if snapshot.get("error"):
            self._set_status("timer.status.bridge_error", error=snapshot["error"])
            return

        self._update_challenge_display(snapshot)

        timers = snapshot.get("challengeTimers") or []
        if not timers:
            self._set_status("timer.status.no_timer")
            self.triggered_thresholds.clear()
            self.start_alert_sent = False
            if self._repeat_timer.IsRunning():
                self._repeat_timer.Stop()
            return

        timer = timers[0]
        remaining = timer.get("remainingSeconds")
        if not isinstance(remaining, (int, float)):
            self._set_status("timer.status.invalid_value")
            return

        current_seconds = max(0, int(remaining))
        self._set_status(
            "timer.status.challenge_timer", value=self._format_seconds(current_seconds)
        )

        if self.start_alert_checkbox.GetValue() and not self.start_alert_sent:
            self._trigger_alert("Countdown started")
            self.start_alert_sent = True
            if self.repeat_alarm_checkbox.GetValue():
                self._repeat_timer.Start(self._repeat_interval_ms)

        for threshold in self._current_thresholds:
            if threshold < 0 or threshold in self.triggered_thresholds:
                continue
            if current_seconds <= threshold:
                self._trigger_alert(f"Timer reached {self._format_seconds(threshold)}")
                self.triggered_thresholds.add(threshold)

    def _trigger_alert(self, message: str) -> None:
        logger.debug(f"Timer alert: {message}")
        self._play_alert()

    def _play_alert(self) -> None:
        if not _SOUND_AVAILABLE:
            logger.warning("Sound playback not available")
            return

        sound_name = self.sound_choice.GetStringSelection()
        sound_key = _SOUND_OPTIONS.get(sound_name, "SystemDefault")

        try:
            winsound.PlaySound(sound_key, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to play sound: {exc}")

    # ------------------------------------------------------------------ bridge watch loop
    def _start_watch_loop(self) -> None:
        if self._closed or self._watcher or self._watch_start_pending:
            return
        self._watch_start_pending = True
        threading.Thread(target=self._watch_start_worker, daemon=True).start()

    def _watch_start_worker(self) -> None:
        try:
            watcher = mtgo_bridge.start_watch(interval_ms=self.WATCH_INTERVAL_MS)
        except FileNotFoundError as exc:
            logger.error("Bridge executable not found: {}", exc)
            if not self._closed:
                wx.CallAfter(self._handle_watch_start_failure, "timer.status.bridge_missing", exc)
            return
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unable to start bridge watcher")
            if not self._closed:
                wx.CallAfter(self._handle_watch_start_failure, "timer.status.bridge_error", exc)
            return

        if self._closed:
            self._stop_watcher_worker(watcher)
            return
        wx.CallAfter(self._complete_watch_start, watcher)

    def _handle_watch_start_failure(self, status_key: str, error: Exception) -> None:
        self._watch_start_pending = False
        if self._closed:
            return
        if status_key == "timer.status.bridge_missing":
            self._set_status(status_key)
        else:
            self._set_status(status_key, error=error)
        wx.CallLater(self.WATCH_RETRY_DELAY_MS, self._start_watch_loop)

    def _complete_watch_start(self, watcher: BridgeWatcher) -> None:
        self._watch_start_pending = False
        if self._closed:
            self._stop_watcher_async(watcher)
            return
        if self._watcher is not None and self._watcher is not watcher:
            self._stop_watcher_async(watcher)
            return
        self._watcher = watcher
        self._watch_timer.Start(self.WATCH_INTERVAL_MS)

    def _stop_watcher_async(self, watcher: BridgeWatcher | None = None) -> None:
        watcher_to_stop = watcher or self._watcher
        if watcher is None:
            self._watcher = None
        if watcher_to_stop is None:
            return
        threading.Thread(
            target=self._stop_watcher_worker,
            args=(watcher_to_stop,),
            daemon=True,
        ).start()

    def _stop_watcher_worker(self, watcher: BridgeWatcher) -> None:
        try:
            watcher.stop()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to stop bridge watcher: {exc}")

    # ------------------------------------------------------------------ timer events
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

    def _on_repeat_timer(self, _event: wx.TimerEvent) -> None:
        if self.monitor_job_active and self.repeat_alarm_checkbox.GetValue():
            self._play_alert()

    def _on_resize(self, event: wx.Event) -> None:
        if self.challenge_text:
            self.challenge_text.Wrap(self._challenge_wrap_width())
        event.Skip()

    # ------------------------------------------------------------------ lifecycle
    def on_close(self, event: wx.CloseEvent) -> None:
        self._closed = True
        self._watch_start_pending = False
        if self._watch_timer.IsRunning():
            self._watch_timer.Stop()
        if self._monitor_timer.IsRunning():
            self._monitor_timer.Stop()
        if self._repeat_timer.IsRunning():
            self._repeat_timer.Stop()
        self._stop_watcher_async()
        event.Skip()
