"""Comp Rules popup shown when a keyword link in oracle text is clicked.

This is a small non-modal frame hosting a ``wx.html.HtmlWindow`` so the
look-and-feel matches the oracle pane that opened it. The frame is reused
for subsequent clicks — opening a second keyword updates the body in place
rather than stacking windows.
"""

from __future__ import annotations

from html import escape

import wx
import wx.html

from utils.constants import DARK_PANEL, PADDING_SM


class RulePopupFrame(wx.Frame):
    """Tiny non-modal frame that displays a single comp rule body."""

    def __init__(self, parent: wx.Window | None = None) -> None:
        super().__init__(
            parent,
            title="Comprehensive Rules",
            size=(520, 360),
            style=wx.DEFAULT_FRAME_STYLE | wx.FRAME_FLOAT_ON_PARENT,
        )
        self.SetBackgroundColour(DARK_PANEL)

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        self._html = wx.html.HtmlWindow(
            self,
            style=wx.html.HW_SCROLLBAR_AUTO | wx.NO_BORDER,
        )
        self._html.SetBackgroundColour(DARK_PANEL)
        self._html.SetBorders(4)
        sizer.Add(self._html, 1, wx.EXPAND | wx.ALL, PADDING_SM)

        self.Bind(wx.EVT_CLOSE, self._on_close)

    def show_rule(self, title: str, rule_id: str, body: str) -> None:
        """Update the popup body and bring it to front (non-modal)."""
        self.SetTitle(f"{rule_id}. {title}")
        self._html.SetPage(_render_rule_html(title=title, rule_id=rule_id, body=body))
        if not self.IsShown():
            self.Show()
        self.Raise()

    def _on_close(self, event: wx.CloseEvent) -> None:
        # Hide rather than destroy so subsequent clicks reuse the same frame.
        if event.CanVeto():
            event.Veto()
            self.Hide()
        else:
            self.Destroy()


def _render_rule_html(*, title: str, rule_id: str, body: str) -> str:
    """Render the rule body as HTML 3.2 — wx.html doesn't grok modern CSS."""
    safe_body = escape(body).replace("\n", "<br>")
    return (
        '<html><body bgcolor="#22272E" text="#E6EDF3">'
        f'<h3><font color="#E6EDF3">{escape(rule_id)}. {escape(title)}</font></h3>'
        f"<hr>"
        f'<font size="-1">{safe_body}</font>'
        "</body></html>"
    )
