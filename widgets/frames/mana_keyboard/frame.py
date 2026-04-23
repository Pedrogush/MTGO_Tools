"""UI construction for the on-screen mana keyboard."""

from __future__ import annotations

from collections.abc import Callable

import wx

from utils.constants import DARK_BG, FULL_MANA_SYMBOLS, LIGHT_TEXT
from utils.mana_icon_factory import ManaIconFactory, type_global_mana_symbol


class ManaKeyboardFrame(wx.Frame):
    def __init__(
        self,
        parent: wx.Window,
        create_button: Callable[[wx.Window, str, Callable[[str], None]], wx.Button],
        on_symbol: Callable[[str], None],
    ) -> None:
        super().__init__(
            parent,
            title="Mana Keyboard",
            size=(620, 330),
            style=wx.CAPTION | wx.CLOSE_BOX | wx.FRAME_TOOL_WINDOW | wx.STAY_ON_TOP,
        )
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        root = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(root)

        info = wx.StaticText(panel, label="Click a symbol to type it anywhere")
        info.SetForegroundColour(LIGHT_TEXT)
        root.Add(info, 0, wx.ALIGN_CENTER | wx.ALL, 8)

        wrap = wx.WrapSizer(wx.HORIZONTAL)
        for token in FULL_MANA_SYMBOLS:
            btn = create_button(panel, token, on_symbol)
            wrap.Add(btn, 0, wx.ALL, 4)
        root.Add(wrap, 1, wx.ALIGN_CENTER_HORIZONTAL | wx.ALL, 10)
        self.CentreOnParent()


def open_mana_keyboard(
    parent: wx.Window,
    mana_icons: ManaIconFactory,
    existing_window: ManaKeyboardFrame | None,
    on_close_callback: Callable[[wx.CloseEvent], None],
) -> ManaKeyboardFrame:
    from widgets.buttons.mana_button import create_mana_button

    if existing_window and existing_window.IsShown():
        existing_window.Raise()
        return existing_window

    def create_button_wrapper(
        panel: wx.Window, token: str, handler: Callable[[str], None]
    ) -> wx.Button:
        return create_mana_button(panel, token, handler, mana_icons)

    frame = ManaKeyboardFrame(parent, create_button_wrapper, type_global_mana_symbol)
    frame.Bind(wx.EVT_CLOSE, on_close_callback)
    frame.Show()
    return frame
