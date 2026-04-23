"""Timer alert viewer package.

Re-exports :class:`TimerAlertFrame` and :func:`main` for external callers, and
surfaces the ``mtgo_bridge``/``wx``/``threading`` modules so tests can
``monkeypatch.setattr(timer_alert.<module>, ...)`` as before.
"""

from __future__ import annotations

import threading  # noqa: F401 - re-exported for tests that monkeypatch timer_alert.threading
from typing import TYPE_CHECKING

import wx  # noqa: F401 - re-exported for tests that monkeypatch timer_alert.wx

from utils import (
    mtgo_bridge,  # noqa: F401 - re-exported for tests that monkeypatch timer_alert.mtgo_bridge  # noqa: E501
)
from widgets.frames.timer_alert.frame import TimerAlertFrame, main

if TYPE_CHECKING:
    pass

__all__ = ["TimerAlertFrame", "main"]
