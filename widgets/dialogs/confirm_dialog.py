"""A yes/no question that does not stop the world while it waits for an answer.

The app asks for confirmation with :func:`wx.MessageBox` in about forty places
and that is fine in all of them: each one answers a click the user just made, so
the modal loop blocks exactly the interaction that opened it.

This is for the other kind — a question that appears *unprompted*. A modal loop
on the main thread stops the automation socket being serviced for as long as it
is up (``docs/WXMSW_BEHAVIOUR.md``; the same reason the menus are data rather
than widgets), so a prompt that can surface on its own can surface in the middle
of something the harness is driving, and the harness has no click to give it and
no way to know it is there. It is also unthemed: wxMSW draws a ``MessageBox`` in
the light system face regardless of process dark mode.

So this is built from the same three ingredients as every other dialog here --
``init_top_level_window``, the type ladder, the button system -- it is modeless,
and it destroys itself on close (a modeless ``wx.Dialog``'s default handling
*hides* rather than destroys; see :mod:`widgets.dialogs.update_check_dialog` for
the same note). The answer comes back as a callback rather than a return value,
because there is no return to wait for.
"""

from __future__ import annotations

from collections.abc import Callable

import wx

from utils.constants import DARK_BG, LIGHT_TEXT, SPACE_MD, SPACE_SM, SUBDUED_TEXT
from widgets.stylize import apply_type_level, init_top_level_window, stylize_button

#: Width the body copy is wrapped to. The window is fitted to its contents, so
#: this is what gives it a width at all.
WRAP_WIDTH = 380


class ConfirmDialog(wx.Dialog):
    """A heading, a line of prose, and two buttons; modeless."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        title: str,
        body: str,
        confirm_label: str,
        dismiss_label: str,
        on_confirm: Callable[[], None],
    ) -> None:
        super().__init__(parent, title=title)
        init_top_level_window(self)
        self.SetBackgroundColour(DARK_BG)
        self._on_confirm = on_confirm

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)

        heading_label = wx.StaticText(panel, label=title)
        heading_label.SetForegroundColour(LIGHT_TEXT)
        apply_type_level(heading_label, "title")
        sizer.Add(heading_label, 0, wx.ALL, SPACE_MD)

        body_label = wx.StaticText(panel, label=body)
        body_label.SetForegroundColour(SUBDUED_TEXT)
        body_label.Wrap(WRAP_WIDTH)
        sizer.Add(body_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        row = wx.BoxSizer(wx.HORIZONTAL)
        row.AddStretchSpacer(1)

        dismiss_btn = wx.Button(panel, label=dismiss_label)
        stylize_button(dismiss_btn, kind="secondary", surface="base")
        dismiss_btn.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        row.Add(dismiss_btn, 0, wx.RIGHT, SPACE_SM)

        self.confirm_btn = wx.Button(panel, label=confirm_label)
        stylize_button(self.confirm_btn, kind="primary", surface="base")
        self.confirm_btn.Bind(wx.EVT_BUTTON, self._on_confirm_clicked)
        self.confirm_btn.SetDefault()
        self.confirm_btn.SetFocus()
        row.Add(self.confirm_btn, 0)

        sizer.Add(row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        panel.SetSizer(sizer)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(panel, 1, wx.EXPAND)
        self.SetSizer(outer)
        self.Fit()
        self.Centre()

        self.Bind(wx.EVT_CLOSE, self._on_close)
        self.Bind(wx.EVT_CHAR_HOOK, self._on_char_hook)

    def _on_confirm_clicked(self, _event: wx.CommandEvent) -> None:
        # Close first: the callback can open windows of its own, and it must not
        # do so behind a dialog that is still on screen.
        self.Close()
        self._on_confirm()

    def _on_close(self, _event: wx.CloseEvent) -> None:
        # Destroy, not hide: wx's default for a modeless dialog leaves the window
        # alive, and the next prompt would then find a stale copy of itself.
        self.Destroy()

    def _on_char_hook(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_ESCAPE:
            self.Close()
            return
        event.Skip()


def show_confirm(
    parent: wx.Window,
    *,
    title: str,
    body: str,
    confirm_label: str,
    dismiss_label: str,
    on_confirm: Callable[[], None],
) -> ConfirmDialog:
    """Open the question, replacing one already on screen.

    Replacing rather than raising: a second copy would be a second question
    about a state the first copy's text may no longer describe.
    """
    for child in parent.GetChildren():
        if isinstance(child, ConfirmDialog):
            child.Destroy()
    dialog = ConfirmDialog(
        parent,
        title=title,
        body=body,
        confirm_label=confirm_label,
        dismiss_label=dismiss_label,
        on_confirm=on_confirm,
    )
    dialog.Show()
    return dialog


__all__ = ["ConfirmDialog", "show_confirm"]
