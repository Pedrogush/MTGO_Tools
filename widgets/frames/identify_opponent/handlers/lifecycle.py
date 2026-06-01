"""Lifecycle hooks for the opponent tracker frame.

Persists config and tears down the radar worker thread, poll timer, and
background worker when the overlay is closed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import OPPONENT_TRACKER_RADAR_THREAD_JOIN_TIMEOUT_SECONDS

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class LifecycleMixin(_Base):
    """Frame close / teardown handling."""

    def on_close(self, event: wx.CloseEvent) -> None:
        self._save_config()

        # Cancel any running radar worker
        if self._radar_worker_thread and self._radar_worker_thread.is_alive():
            self._radar_cancel_requested = True
            # Give it a moment to clean up
            self._radar_worker_thread.join(
                timeout=OPPONENT_TRACKER_RADAR_THREAD_JOIN_TIMEOUT_SECONDS
            )

        if self._poll_timer.IsRunning():
            self._poll_timer.Stop()
        self._bg_worker.shutdown(timeout=5.0)
        event.Skip()
