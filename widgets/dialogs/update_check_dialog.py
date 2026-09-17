"""The answer to *File ▸ Check for updates* when there is nothing to download (#1041).

Two of the three outcomes of an explicitly requested check have no update to
offer — "you are on the newest version" and "GitHub could not be reached" — and
both still have to be *said*. Failing silently is the bug the menu item exists to
fix, one level up: a user who asked and saw nothing happen cannot tell a working
check from a broken one. The third outcome reuses
:class:`widgets.dialogs.update_dialog.UpdateDialog`, which is why this window has
no update-available face.

Why not ``wx.MessageBox``
-------------------------
The app uses it elsewhere, and it would have been one line. It is also **modal**,
and a modal loop on the main thread stops the automation socket being serviced
for as long as it is up (``docs/WXMSW_BEHAVIOUR.md``; the same reason the menus
are data rather than widgets). That would make this feature the one outcome of
the app that cannot be driven or screenshotted by the harness — including in the
smoke test for the feature itself. It is also unthemed: wxMSW draws a
``MessageBox`` in the light system face regardless of process dark mode.

So this is a modeless window on the same three ingredients every other dialog in
the app is built from — ``init_top_level_window``, the type ladder, the button
system — and it destroys itself on close (a modeless ``wx.Dialog``'s default
handling *hides* rather than destroys; see the update dialog for the same note).
"""

from __future__ import annotations

import wx

from utils.constants import DARK_BG, LIGHT_TEXT, SPACE_MD, SUBDUED_TEXT
from utils.i18n import t
from widgets.stylize import apply_type_level, init_top_level_window, stylize_button

#: Width the body copy is wrapped to. The window is fitted to its contents, so
#: this is what gives it a width at all. Narrower than the updater's 420: this
#: one carries a sentence, not a paragraph about checksums.
WRAP_WIDTH = 360


class UpdateCheckNoticeDialog(wx.Dialog):
    """A heading, a line of prose and a Close button. Nothing is pending behind it."""

    def __init__(self, parent: wx.Window, heading: str, body: str) -> None:
        super().__init__(parent, title=t("app.update_check.title"))
        init_top_level_window(self)
        self.SetBackgroundColour(DARK_BG)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)

        heading_label = wx.StaticText(panel, label=heading)
        heading_label.SetForegroundColour(LIGHT_TEXT)
        apply_type_level(heading_label, "title")
        sizer.Add(heading_label, 0, wx.ALL, SPACE_MD)

        body_label = wx.StaticText(panel, label=body)
        body_label.SetForegroundColour(SUBDUED_TEXT)
        body_label.Wrap(WRAP_WIDTH)
        sizer.Add(body_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.AddStretchSpacer(1)
        close_btn = wx.Button(panel, label=t("app.update.btn.close"))
        stylize_button(close_btn, kind="primary", surface="base")
        close_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        close_btn.SetDefault()
        close_btn.SetFocus()
        row.Add(close_btn, 0)
        sizer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.Fit()
        self.Centre()

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _on_close(self, _event: wx.CloseEvent) -> None:
        # Destroy, not hide: wx's default for a modeless dialog is EndDialog,
        # which leaves the window alive and would have show_update_check_notice
        # raise a stale copy the next time the user asked.
        self.Destroy()

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()


def show_update_check_notice(parent: wx.Window, heading: str, body: str) -> UpdateCheckNoticeDialog:
    """Open the notice, replacing one already on screen.

    Replacing rather than raising, unlike the updater: that window owns a
    download and a second one would start a second transfer, while this one is a
    sentence whose *text* is the thing that changed. Leaving the old copy up
    would answer the user's second click with the first click's answer.
    """
    for child in parent.GetChildren():
        if isinstance(child, UpdateCheckNoticeDialog):
            child.Destroy()
    dialog = UpdateCheckNoticeDialog(parent, heading, body)
    dialog.Show()
    return dialog


__all__ = ["UpdateCheckNoticeDialog", "show_update_check_notice"]
