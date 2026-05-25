"""Timer alert viewer package.

Re-exports :class:`TimerAlertFrame` and :func:`main` for external callers, and
surfaces ``wx``/``threading`` modules so tests can
``monkeypatch.setattr(timer_alert.<module>, ...)`` as before.
"""

from __future__ import annotations

import threading  # noqa: F401 - re-exported for tests that monkeypatch timer_alert.threading

import wx  # noqa: F401 - re-exported for tests that monkeypatch timer_alert.wx

from widgets.frames.timer_alert.frame import TimerAlertFrame, main

__all__ = ["TimerAlertFrame", "main"]
