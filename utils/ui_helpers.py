"""Utility helpers for wx UI interactions shared across widgets."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx
from loguru import logger


def widget_exists(window: wx.Window | None) -> bool:
    if window is None:
        return False
    try:
        return bool(window.IsShown())
    except wx.PyDeadObjectError:
        return False


def open_child_window(
    owner: Any,
    attr: str,
    window_class: type[wx.Window],
    title: str,
    on_close: Callable[[wx.CloseEvent, str], None],
    *args,
    **kwargs,
) -> wx.Window | None:
    """Create or raise a child window tracked on the parent frame."""
    existing = getattr(owner, attr, None)
    if widget_exists(existing):
        existing.Raise()
        return existing
    try:
        window = window_class(owner, *args, **kwargs)
        window.Bind(wx.EVT_CLOSE, lambda evt: on_close(evt, attr))
        window.Show()
        setattr(owner, attr, window)
        return window
    except Exception as exc:  # pragma: no cover - UI side-effects
        logger.error(f"Failed to open {title.lower()}: {exc}")
        wx.MessageBox(
            f"Unable to open {title.lower()}:\n{exc}",
            title,
            wx.OK | wx.ICON_ERROR,
        )
        return None
