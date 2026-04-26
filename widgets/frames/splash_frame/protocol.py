"""Shared ``self`` contract that the :class:`LoadingFrame` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

import wx


class LoadingFrameProto(Protocol):
    """Cross-mixin ``self`` surface for ``LoadingFrame``."""

    _start: float
    _min_duration: float
    _max_duration: float
    _ready: bool
    _finished: bool
    _on_ready: Callable[[], None] | None
    _timer: wx.Timer

    def _maybe_finish(self) -> None: ...

    # ``LoadingFrame`` extends ``wx.Frame``; mixin code calls these wx methods.
    def Hide(self) -> bool: ...
    def Destroy(self) -> bool: ...
