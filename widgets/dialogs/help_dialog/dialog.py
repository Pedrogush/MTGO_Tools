"""Help viewer for MTGO Tools using wxPython's HTML Help system."""

from __future__ import annotations

import wx
import wx.html

from utils.constants.paths import resource_path

_HHP_FILE = resource_path("help", "mtgo_tools.hhp")

_controller: wx.html.HtmlHelpController | None = None


def _get_controller() -> wx.html.HtmlHelpController:
    """Return a shared HtmlHelpController, creating it on first call."""
    global _controller
    if _controller is None:
        _controller = wx.html.HtmlHelpController(style=wx.html.HF_DEFAULT_STYLE)
        if _HHP_FILE.is_file():
            _controller.AddBook(str(_HHP_FILE), False)
    return _controller


def show_help(parent: wx.Window | None = None, topic: str | None = None) -> None:
    """Open the help viewer, optionally jumping to a specific topic HTML file."""
    ctrl = _get_controller()
    if topic:
        ctrl.Display(topic)
    else:
        ctrl.DisplayContents()
