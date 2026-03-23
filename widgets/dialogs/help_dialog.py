"""Help viewer for MTGO Tools using wxPython's HTML Help system."""

from __future__ import annotations

import os

import wx
import wx.html

_HELP_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "help")
_HHP_FILE = os.path.join(_HELP_DIR, "mtgo_tools.hhp")

_controller: wx.html.HtmlHelpController | None = None


def _get_controller() -> wx.html.HtmlHelpController:
    """Return a shared HtmlHelpController, creating it on first call."""
    global _controller
    if _controller is None:
        _controller = wx.html.HtmlHelpController(style=wx.html.HF_DEFAULT_STYLE)
        hhp = os.path.normpath(_HHP_FILE)
        if os.path.isfile(hhp):
            _controller.AddBook(hhp, False)
    return _controller


def show_help(parent: wx.Window | None = None, topic: str | None = None) -> None:
    """Open the help viewer, optionally jumping to a specific topic HTML file."""
    ctrl = _get_controller()
    if topic:
        ctrl.Display(topic)
    else:
        ctrl.DisplayContents()
