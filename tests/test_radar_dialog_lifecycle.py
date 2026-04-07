"""Headless lifecycle tests for radar dialog background work."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("wx")

import widgets.panels.radar_panel as radar_panel

RadarDialog = radar_panel.RadarDialog


class _AliveThread:
    def is_alive(self) -> bool:
        return True


class _StoppedThread:
    def is_alive(self) -> bool:
        return False


class _FakeWorker:
    def __init__(self) -> None:
        self.shutdown_calls: list[float] = []

    def shutdown(self, timeout: float = 10.0) -> None:
        self.shutdown_calls.append(timeout)


def _make_dialog(worker_thread) -> RadarDialog:  # noqa: ANN001
    dialog = RadarDialog.__new__(RadarDialog)
    dialog.worker_thread = worker_thread
    dialog._worker = _FakeWorker()
    dialog.cancel_requested = False
    dialog.IsModal = MagicMock(return_value=False)
    dialog.EndModal = MagicMock()
    dialog.Close = MagicMock()
    return dialog


def test_close_button_cancels_pending_radar_worker(monkeypatch) -> None:
    dialog = _make_dialog(_AliveThread())
    event = MagicMock()

    monkeypatch.setattr(radar_panel.wx, "MessageBox", lambda *_args, **_kwargs: radar_panel.wx.YES)

    RadarDialog._on_close(dialog, event)

    assert dialog.cancel_requested is True
    assert dialog.worker_thread is None
    assert dialog._worker.shutdown_calls == [2.0]
    dialog.Close.assert_called_once_with()
    event.Skip.assert_not_called()


def test_close_event_skips_instead_of_reclosing(monkeypatch) -> None:
    dialog = _make_dialog(_StoppedThread())
    skipped = []

    class CloseEvent:
        def Skip(self) -> None:
            skipped.append(True)

    monkeypatch.setattr(radar_panel.wx, "CloseEvent", CloseEvent)
    event = CloseEvent()

    RadarDialog._on_close(dialog, event)

    assert dialog._worker.shutdown_calls == [0.2]
    assert skipped == [True]
    dialog.Close.assert_not_called()
