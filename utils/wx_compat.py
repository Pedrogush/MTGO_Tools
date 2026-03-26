"""Minimal wx import compatibility for headless test environments."""

from __future__ import annotations

from types import SimpleNamespace


class _WxFallback(SimpleNamespace):
    """Fallback object that lets wx-dependent modules import without wx installed."""

    Frame = object
    Panel = object
    Window = object
    Button = object
    StaticText = object
    ListBox = object
    BoxSizer = object
    Timer = object
    Choice = object
    CheckBox = object
    SpinCtrl = object
    TextCtrl = object
    ListCtrl = object
    StaticLine = object
    Gauge = object
    Dialog = object
    App = object
    CommandEvent = object
    CloseEvent = object

    def __getattr__(self, _name: str):
        return 0


def get_wx():
    """Return the real ``wx`` module when available, else a minimal fallback."""
    try:
        import wx

        return wx
    except ModuleNotFoundError:
        return _WxFallback()
