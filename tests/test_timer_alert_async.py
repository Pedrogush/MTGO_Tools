"""Headless tests for TimerAlertFrame bridge watcher lifecycle."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import widgets.frames.timer_alert as timer_alert
import widgets.frames.timer_alert.handlers as timer_alert_handlers

TimerAlertFrame = timer_alert.TimerAlertFrame


def _make_frame() -> TimerAlertFrame:
    frame = TimerAlertFrame.__new__(TimerAlertFrame)
    frame.WATCH_INTERVAL_MS = 750
    frame.WATCH_RETRY_DELAY_MS = 5000
    frame._watcher = None
    frame._watch_start_pending = False
    frame._closed = False
    frame._watch_timer = MagicMock()
    frame._monitor_timer = MagicMock()
    frame._repeat_timer = MagicMock()
    frame._set_status = MagicMock()
    frame.controller = MagicMock()
    return frame


class _FakeValue:
    """Tiny stand-in for a wx control exposing GetValue (and SetValue)."""

    def __init__(self, value: object) -> None:
        self._value = value

    def GetValue(self) -> object:
        return self._value

    def SetValue(self, value: object) -> None:
        self._value = value


class _FakeThresholdPanel:
    """Records enable/disable calls so monitoring can be asserted by value."""

    def __init__(self, seconds: int | None) -> None:
        self._seconds = seconds
        self.enabled = True
        self.time_input = _FakeValue("" if seconds is None else str(seconds))

    def get_seconds(self) -> int | None:
        return self._seconds

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled


def _make_monitor_frame(
    *,
    panels: list[_FakeThresholdPanel] | None = None,
    poll_value: object = 1000,
    repeat_seconds: int = 3,
) -> TimerAlertFrame:
    """Frame wired for the monitoring/alert surface with fake widgets.

    Records ``_set_status`` calls as ``(key, kwargs)`` tuples and ``_play_alert``
    invocations, so behavior is asserted by value rather than by mock interaction.
    """
    frame = _make_frame()
    frame.status_calls: list[tuple[str, dict[str, object]]] = []
    frame._set_status = lambda key, **kwargs: frame.status_calls.append((key, kwargs))
    frame.alert_messages: list[str] = []
    frame._trigger_alert = lambda message: frame.alert_messages.append(message)
    frame.play_alert_count = 0

    def _count_play_alert() -> None:
        frame.play_alert_count += 1

    frame._play_alert = _count_play_alert
    frame._format_seconds = lambda value: f"fmt:{value}"
    frame._update_challenge_display = MagicMock()

    frame.threshold_panels = panels if panels is not None else [_FakeThresholdPanel(60)]
    frame.poll_interval_ctrl = _FakeValue(poll_value)
    frame.repeat_interval_ctrl = _FakeValue(repeat_seconds)
    frame.start_alert_checkbox = _FakeValue(False)
    frame.repeat_alarm_checkbox = _FakeValue(False)

    frame._current_thresholds = []
    frame._monitor_interval_ms = 0
    frame._repeat_interval_ms = 0
    frame.triggered_thresholds = set()
    frame.start_alert_sent = False
    frame.monitor_job_active = False
    frame._last_snapshot = None
    return frame


def _make_fake_thread(threads: list[object]):
    class FakeThread:
        def __init__(self, *, target, daemon: bool, args: tuple[object, ...] = ()) -> None:
            self.target = target
            self.args = args
            self.daemon = daemon
            self.started = False
            threads.append(self)

        def start(self) -> None:
            self.started = True

    return FakeThread


def _patch_call_after(
    monkeypatch, calls: list[tuple[object, tuple[object, ...], dict[str, object]]]
):
    monkeypatch.setattr(
        timer_alert.wx,
        "CallAfter",
        lambda func, *args, **kwargs: calls.append((func, args, kwargs)),
    )


def test_start_watch_loop_runs_bridge_start_in_background(monkeypatch) -> None:
    frame = _make_frame()
    watcher = MagicMock()
    start_watch_calls: list[int] = []
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []
    threads: list[object] = []

    def fake_start_watch(*, interval_ms: int):
        start_watch_calls.append(interval_ms)
        return watcher

    frame.controller.mtgo_bridge_service.start_watch = fake_start_watch
    _patch_call_after(monkeypatch, call_after_calls)
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._start_watch_loop(frame)

    assert frame._watch_start_pending is True
    assert start_watch_calls == []
    assert len(threads) == 1
    assert threads[0].started is True
    assert threads[0].daemon is True

    threads[0].target(*threads[0].args)

    assert start_watch_calls == [frame.WATCH_INTERVAL_MS]
    assert call_after_calls == [(frame._complete_watch_start, (watcher,), {})]

    # Medium finding: the success target was scheduled but never invoked, so its
    # effects (clearing the pending flag, storing the watcher, starting the
    # watch timer) went unverified. Invoke it and assert the outcome.
    TimerAlertFrame._complete_watch_start(frame, watcher)

    assert frame._watcher is watcher
    assert frame._watch_start_pending is False
    frame._watch_timer.Start.assert_called_once_with(frame.WATCH_INTERVAL_MS)


def test_on_close_stops_existing_watcher_in_background(monkeypatch) -> None:
    frame = _make_frame()
    watcher = MagicMock()
    frame._watcher = watcher
    frame._watch_timer.IsRunning.return_value = True
    frame._monitor_timer.IsRunning.return_value = True
    frame._repeat_timer.IsRunning.return_value = True
    threads: list[object] = []

    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))
    event = MagicMock()

    TimerAlertFrame.on_close(frame, event)

    assert frame._closed is True
    assert frame._watcher is None
    frame._watch_timer.Stop.assert_called_once_with()
    frame._monitor_timer.Stop.assert_called_once_with()
    frame._repeat_timer.Stop.assert_called_once_with()
    watcher.stop.assert_not_called()
    assert len(threads) == 1
    assert threads[0].started is True
    assert threads[0].daemon is True

    threads[0].target(*threads[0].args)

    watcher.stop.assert_called_once_with()
    event.Skip.assert_called_once_with()


@pytest.mark.parametrize(
    ("status_key", "exc"),
    [
        ("timer.status.bridge_missing", FileNotFoundError("bridge.exe")),
        ("timer.status.bridge_error", RuntimeError("boom")),
    ],
)
def test_watch_start_worker_schedules_failure_handler(monkeypatch, status_key, exc) -> None:
    """A FileNotFoundError / generic Exception in start_watch schedules the
    failure handler with the right status key and exception, off the main thread.
    """
    frame = _make_frame()
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def fake_start_watch(*, interval_ms: int):
        raise exc

    frame.controller.mtgo_bridge_service.start_watch = fake_start_watch
    _patch_call_after(monkeypatch, call_after_calls)

    TimerAlertFrame._watch_start_worker(frame)

    assert call_after_calls == [(frame._handle_watch_start_failure, (status_key, exc), {})]


def test_watch_start_worker_skips_failure_handler_when_closed(monkeypatch) -> None:
    """If the frame closed during the failed start, no handler is scheduled."""
    frame = _make_frame()
    frame._closed = True
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    def fake_start_watch(*, interval_ms: int):
        raise FileNotFoundError("bridge.exe")

    frame.controller.mtgo_bridge_service.start_watch = fake_start_watch
    _patch_call_after(monkeypatch, call_after_calls)

    TimerAlertFrame._watch_start_worker(frame)

    assert call_after_calls == []


@pytest.mark.parametrize(
    ("status_key", "expected_kwargs"),
    [
        ("timer.status.bridge_missing", {}),
        ("timer.status.bridge_error", {"error": "passed-error"}),
    ],
)
def test_handle_watch_start_failure_sets_status_and_schedules_retry(
    monkeypatch, status_key, expected_kwargs
) -> None:
    """The failure handler clears the pending flag, surfaces the status, and
    schedules a retry of the watch loop after WATCH_RETRY_DELAY_MS.
    """
    frame = _make_frame()
    frame._watch_start_pending = True
    error = "passed-error"
    call_later_calls: list[tuple[int, object]] = []
    monkeypatch.setattr(
        timer_alert.wx,
        "CallLater",
        lambda delay, func, *a, **k: call_later_calls.append((delay, func)),
    )

    TimerAlertFrame._handle_watch_start_failure(frame, status_key, error)

    assert frame._watch_start_pending is False
    if expected_kwargs:
        frame._set_status.assert_called_once_with(status_key, error=error)
    else:
        frame._set_status.assert_called_once_with(status_key)
    assert call_later_calls == [(frame.WATCH_RETRY_DELAY_MS, frame._start_watch_loop)]


def test_handle_watch_start_failure_noops_when_closed(monkeypatch) -> None:
    """When already closed, the handler clears the pending flag but does not set
    status or schedule a retry.
    """
    frame = _make_frame()
    frame._watch_start_pending = True
    frame._closed = True
    call_later_calls: list[tuple[int, object]] = []
    monkeypatch.setattr(
        timer_alert.wx,
        "CallLater",
        lambda delay, func, *a, **k: call_later_calls.append((delay, func)),
    )

    TimerAlertFrame._handle_watch_start_failure(frame, "timer.status.bridge_error", RuntimeError())

    assert frame._watch_start_pending is False
    frame._set_status.assert_not_called()
    assert call_later_calls == []


@pytest.mark.parametrize(
    ("attr", "value"),
    [
        ("_closed", True),
        ("_watcher", MagicMock()),
        ("_watch_start_pending", True),
    ],
)
def test_start_watch_loop_guard_blocks_duplicate_start(monkeypatch, attr, value) -> None:
    """The early-return guard prevents spawning a watcher thread when closed,
    when a watcher already exists, or when a start is already pending.
    """
    frame = _make_frame()
    setattr(frame, attr, value)
    threads: list[object] = []
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._start_watch_loop(frame)

    assert threads == []
    # The guard must not flip the pending flag (except where it was already set).
    if attr != "_watch_start_pending":
        assert frame._watch_start_pending is False


def test_watch_start_worker_stops_watcher_when_closed_after_success(monkeypatch) -> None:
    """If the frame closed while start_watch was running, the freshly-created
    watcher is stopped synchronously (no CallAfter) to avoid leaking it.
    """
    frame = _make_frame()
    frame._closed = True
    watcher = MagicMock()
    call_after_calls: list[tuple[object, tuple[object, ...], dict[str, object]]] = []

    frame.controller.mtgo_bridge_service.start_watch = lambda *, interval_ms: watcher
    _patch_call_after(monkeypatch, call_after_calls)

    TimerAlertFrame._watch_start_worker(frame)

    watcher.stop.assert_called_once_with()
    assert call_after_calls == []


def test_complete_watch_start_stops_stale_watcher(monkeypatch) -> None:
    """If a different watcher is already installed, the incoming watcher is
    stopped and the existing one is left untouched.
    """
    frame = _make_frame()
    existing = MagicMock()
    incoming = MagicMock()
    frame._watcher = existing
    frame._watch_start_pending = True
    threads: list[object] = []
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._complete_watch_start(frame, incoming)

    assert frame._watch_start_pending is False
    assert frame._watcher is existing
    frame._watch_timer.Start.assert_not_called()
    assert len(threads) == 1
    assert threads[0].args == (incoming,)
    threads[0].target(*threads[0].args)
    incoming.stop.assert_called_once_with()
    existing.stop.assert_not_called()


def test_complete_watch_start_stops_watcher_when_closed(monkeypatch) -> None:
    """If the frame closed before completion runs, the watcher is stopped and
    not installed.
    """
    frame = _make_frame()
    frame._closed = True
    frame._watch_start_pending = True
    watcher = MagicMock()
    threads: list[object] = []
    monkeypatch.setattr(timer_alert.threading, "Thread", _make_fake_thread(threads))

    TimerAlertFrame._complete_watch_start(frame, watcher)

    assert frame._watch_start_pending is False
    assert frame._watcher is None
    frame._watch_timer.Start.assert_not_called()
    assert len(threads) == 1
    threads[0].target(*threads[0].args)
    watcher.stop.assert_called_once_with()


# --------------------------------------------------------------------- monitoring


def test_start_monitoring_noops_when_already_active() -> None:
    frame = _make_monitor_frame()
    frame.monitor_job_active = True

    TimerAlertFrame.start_monitoring(frame)

    assert frame.status_calls == [("timer.status.already_monitoring", {})]
    frame._monitor_timer.Start.assert_not_called()
    assert frame.threshold_panels[0].enabled is True


def test_start_monitoring_requires_thresholds() -> None:
    frame = _make_monitor_frame(panels=[_FakeThresholdPanel(None)])

    TimerAlertFrame.start_monitoring(frame)

    assert frame.status_calls == [("timer.status.no_thresholds", {})]
    assert frame.monitor_job_active is False
    frame._monitor_timer.Start.assert_not_called()


def test_start_monitoring_rejects_invalid_poll_interval() -> None:
    frame = _make_monitor_frame(poll_value="not-a-number")

    TimerAlertFrame.start_monitoring(frame)

    assert frame.status_calls == [("timer.status.invalid_poll_interval", {})]
    assert frame.monitor_job_active is False
    frame._monitor_timer.Start.assert_not_called()


def test_start_monitoring_clamps_poll_interval_floor() -> None:
    frame = _make_monitor_frame(poll_value=10)

    TimerAlertFrame.start_monitoring(frame)

    # The 250ms floor wins over the requested 10ms.
    assert frame._monitor_interval_ms == 250
    frame._monitor_timer.Start.assert_called_once_with(250)


def test_start_monitoring_activates_and_disables_panels() -> None:
    panels = [_FakeThresholdPanel(30), _FakeThresholdPanel(120)]
    frame = _make_monitor_frame(panels=panels, poll_value=1000, repeat_seconds=4)
    frame.triggered_thresholds = {99}
    frame.start_alert_sent = True

    TimerAlertFrame.start_monitoring(frame)

    assert frame.monitor_job_active is True
    # Thresholds parsed and sorted descending by the real properties mixin.
    assert frame._current_thresholds == [120, 30]
    assert frame._monitor_interval_ms == 1000
    assert frame._repeat_interval_ms == 4000
    assert frame.triggered_thresholds == set()
    assert frame.start_alert_sent is False
    assert all(panel.enabled is False for panel in panels)
    frame._monitor_timer.Start.assert_called_once_with(1000)
    # "monitoring" status is set before the initial step; the step then runs
    # with no snapshot and reports waiting-for-data.
    assert ("timer.status.monitoring", {}) in frame.status_calls
    assert ("timer.status.waiting_data", {}) in frame.status_calls


def test_stop_monitoring_stops_running_timers_and_reenables_panels() -> None:
    panels = [_FakeThresholdPanel(30), _FakeThresholdPanel(60)]
    frame = _make_monitor_frame(panels=panels)
    frame.monitor_job_active = True
    for panel in panels:
        panel.enabled = False
    frame._monitor_timer.IsRunning.return_value = True
    frame._repeat_timer.IsRunning.return_value = True

    TimerAlertFrame.stop_monitoring(frame)

    frame._monitor_timer.Stop.assert_called_once_with()
    frame._repeat_timer.Stop.assert_called_once_with()
    assert frame.monitor_job_active is False
    assert all(panel.enabled is True for panel in panels)
    assert frame.status_calls == [("timer.status.stopped", {})]


def test_stop_monitoring_skips_stop_when_timers_idle() -> None:
    frame = _make_monitor_frame()
    frame.monitor_job_active = True
    frame._monitor_timer.IsRunning.return_value = False
    frame._repeat_timer.IsRunning.return_value = False

    TimerAlertFrame.stop_monitoring(frame)

    frame._monitor_timer.Stop.assert_not_called()
    frame._repeat_timer.Stop.assert_not_called()
    assert frame.monitor_job_active is False


def test_test_alert_delegates_to_play_alert() -> None:
    frame = _make_monitor_frame()

    TimerAlertFrame.test_alert(frame)

    assert frame.play_alert_count == 1


# ------------------------------------------------------------------ monitor step


def test_monitor_step_waits_for_data_when_no_snapshot() -> None:
    frame = _make_monitor_frame()
    frame._last_snapshot = None

    TimerAlertFrame._monitor_timer_step(frame)

    assert frame.status_calls == [("timer.status.waiting_data", {})]


def test_monitor_step_surfaces_bridge_error() -> None:
    frame = _make_monitor_frame()
    frame._last_snapshot = {"error": "boom"}

    TimerAlertFrame._monitor_timer_step(frame)

    assert frame.status_calls == [("timer.status.bridge_error", {"error": "boom"})]


def test_monitor_step_reports_no_timer_and_resets_state() -> None:
    frame = _make_monitor_frame()
    frame._last_snapshot = {"challengeTimers": []}
    frame.triggered_thresholds = {30}
    frame.start_alert_sent = True
    frame._repeat_timer.IsRunning.return_value = True

    TimerAlertFrame._monitor_timer_step(frame)

    assert frame.status_calls == [("timer.status.no_timer", {})]
    assert frame.triggered_thresholds == set()
    assert frame.start_alert_sent is False
    frame._repeat_timer.Stop.assert_called_once_with()
    frame._update_challenge_display.assert_called_once_with(frame._last_snapshot)


def test_monitor_step_rejects_non_numeric_remaining() -> None:
    frame = _make_monitor_frame()
    frame._last_snapshot = {"challengeTimers": [{"remainingSeconds": "soon"}]}

    TimerAlertFrame._monitor_timer_step(frame)

    assert frame.status_calls == [("timer.status.invalid_value", {})]


def test_monitor_step_fires_threshold_alerts_once() -> None:
    frame = _make_monitor_frame()
    frame._current_thresholds = [120, 30]
    frame._last_snapshot = {"challengeTimers": [{"remainingSeconds": 25}]}

    TimerAlertFrame._monitor_timer_step(frame)

    # Both thresholds are at/above 25 remaining seconds, so both fire once.
    assert frame.alert_messages == ["Timer reached fmt:120", "Timer reached fmt:30"]
    assert frame.triggered_thresholds == {120, 30}

    # A second step at the same remaining time does not re-fire.
    frame.alert_messages.clear()
    TimerAlertFrame._monitor_timer_step(frame)
    assert frame.alert_messages == []


def test_monitor_step_skips_negative_thresholds() -> None:
    frame = _make_monitor_frame()
    frame._current_thresholds = [-1]
    frame._last_snapshot = {"challengeTimers": [{"remainingSeconds": 5}]}

    TimerAlertFrame._monitor_timer_step(frame)

    assert frame.alert_messages == []
    assert frame.triggered_thresholds == set()


def test_monitor_step_sends_start_alert_and_starts_repeat_timer() -> None:
    frame = _make_monitor_frame(repeat_seconds=2)
    frame._repeat_interval_ms = 2000
    frame._current_thresholds = []
    frame.start_alert_checkbox.SetValue(True)
    frame.repeat_alarm_checkbox.SetValue(True)
    frame._last_snapshot = {"challengeTimers": [{"remainingSeconds": 600}]}

    TimerAlertFrame._monitor_timer_step(frame)

    assert frame.alert_messages == ["Countdown started"]
    assert frame.start_alert_sent is True
    frame._repeat_timer.Start.assert_called_once_with(2000)


def test_monitor_step_start_alert_fires_only_once() -> None:
    frame = _make_monitor_frame()
    frame._current_thresholds = []
    frame.start_alert_checkbox.SetValue(True)
    frame._last_snapshot = {"challengeTimers": [{"remainingSeconds": 600}]}

    TimerAlertFrame._monitor_timer_step(frame)
    frame.alert_messages.clear()
    TimerAlertFrame._monitor_timer_step(frame)

    assert frame.alert_messages == []


# ------------------------------------------------------------------ timer events


def test_on_watch_timer_noops_without_watcher() -> None:
    frame = _make_monitor_frame()
    frame._watcher = None

    TimerAlertFrame._on_watch_timer(frame, MagicMock())

    assert frame._last_snapshot is None
    frame._update_challenge_display.assert_not_called()


def test_on_watch_timer_ignores_empty_payload() -> None:
    frame = _make_monitor_frame()
    frame._watcher = MagicMock()
    frame._watcher.latest.return_value = None

    TimerAlertFrame._on_watch_timer(frame, MagicMock())

    assert frame._last_snapshot is None
    frame._update_challenge_display.assert_not_called()


def test_on_watch_timer_stores_and_displays_payload() -> None:
    frame = _make_monitor_frame()
    payload = {"challengeTimers": [{"remainingSeconds": 10}]}
    frame._watcher = MagicMock()
    frame._watcher.latest.return_value = payload

    TimerAlertFrame._on_watch_timer(frame, MagicMock())

    assert frame._last_snapshot is payload
    frame._update_challenge_display.assert_called_once_with(payload)


def test_on_monitor_timer_runs_step() -> None:
    frame = _make_monitor_frame()
    frame._last_snapshot = None

    TimerAlertFrame._on_monitor_timer(frame, MagicMock())

    assert frame.status_calls == [("timer.status.waiting_data", {})]


def test_on_repeat_timer_plays_alert_when_active_and_enabled() -> None:
    frame = _make_monitor_frame()
    frame.monitor_job_active = True
    frame.repeat_alarm_checkbox.SetValue(True)

    TimerAlertFrame._on_repeat_timer(frame, MagicMock())

    assert frame.play_alert_count == 1


@pytest.mark.parametrize(
    ("active", "repeat_enabled"),
    [(False, True), (True, False), (False, False)],
)
def test_on_repeat_timer_silent_when_inactive_or_disabled(active, repeat_enabled) -> None:
    frame = _make_monitor_frame()
    frame.monitor_job_active = active
    frame.repeat_alarm_checkbox.SetValue(repeat_enabled)

    TimerAlertFrame._on_repeat_timer(frame, MagicMock())

    assert frame.play_alert_count == 0


# ------------------------------------------------------------------ alert playback


def test_play_alert_uses_mapped_sound_alias(monkeypatch) -> None:
    frame = _make_frame()
    frame.sound_choice = MagicMock()
    frame.sound_choice.GetStringSelection.return_value = "Alert"
    fake_winsound = MagicMock()
    fake_winsound.SND_ALIAS = 0x10000
    fake_winsound.SND_ASYNC = 0x0001
    monkeypatch.setattr(timer_alert_handlers, "_SOUND_AVAILABLE", True)
    monkeypatch.setattr(timer_alert_handlers, "winsound", fake_winsound, raising=False)

    TimerAlertFrame._play_alert(frame)

    fake_winsound.PlaySound.assert_called_once_with(
        "SystemExclamation",
        fake_winsound.SND_ALIAS | fake_winsound.SND_ASYNC,
    )


def test_play_alert_falls_back_to_default_alias(monkeypatch) -> None:
    frame = _make_frame()
    frame.sound_choice = MagicMock()
    frame.sound_choice.GetStringSelection.return_value = "Unknown Sound"
    fake_winsound = MagicMock()
    monkeypatch.setattr(timer_alert_handlers, "_SOUND_AVAILABLE", True)
    monkeypatch.setattr(timer_alert_handlers, "winsound", fake_winsound, raising=False)

    TimerAlertFrame._play_alert(frame)

    sound_key = fake_winsound.PlaySound.call_args.args[0]
    assert sound_key == "SystemDefault"


def test_play_alert_noops_when_sound_unavailable(monkeypatch) -> None:
    frame = _make_frame()
    frame.sound_choice = MagicMock()
    fake_winsound = MagicMock()
    monkeypatch.setattr(timer_alert_handlers, "_SOUND_AVAILABLE", False)
    monkeypatch.setattr(timer_alert_handlers, "winsound", fake_winsound, raising=False)

    TimerAlertFrame._play_alert(frame)

    fake_winsound.PlaySound.assert_not_called()
    frame.sound_choice.GetStringSelection.assert_not_called()


def test_play_alert_swallows_playback_errors(monkeypatch) -> None:
    frame = _make_frame()
    frame.sound_choice = MagicMock()
    frame.sound_choice.GetStringSelection.return_value = "Beep"
    fake_winsound = MagicMock()
    fake_winsound.PlaySound.side_effect = RuntimeError("device busy")
    monkeypatch.setattr(timer_alert_handlers, "_SOUND_AVAILABLE", True)
    monkeypatch.setattr(timer_alert_handlers, "winsound", fake_winsound, raising=False)

    # Must not propagate; playback failure is logged and ignored.
    TimerAlertFrame._play_alert(frame)

    fake_winsound.PlaySound.assert_called_once()
