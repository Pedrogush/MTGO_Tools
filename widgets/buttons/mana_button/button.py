"""
Mana Button - Creates buttons for mana symbols with icons or text.

Provides functionality to create wxPython buttons that display mana symbols,
either as bitmap icons or as styled text.
"""

from collections.abc import Callable

import wx

from utils.constants import DARK_ALT, LIGHT_TEXT
from utils.mana_icon_factory import ManaIconFactory


def get_mana_font(size: int = 14, parent_font: wx.Font | None = None) -> wx.Font:
    if ManaIconFactory._FONT_LOADED:
        return wx.Font(
            size,
            wx.FONTFAMILY_DEFAULT,
            wx.FONTSTYLE_NORMAL,
            wx.FONTWEIGHT_NORMAL,
            False,
            ManaIconFactory._FONT_NAME,
        )
    # Fallback to parent font or system default
    if parent_font:
        font = parent_font
    else:
        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
    font.SetPointSize(size)
    font.MakeBold()
    return font


def create_mana_button(
    parent: wx.Window,
    token: str,
    handler: Callable[[str], None],
    mana_icons: ManaIconFactory,
    font_size: int = 15,
) -> wx.Button:
    bmp: wx.Bitmap | None = None
    try:
        bmp = mana_icons.bitmap_for_symbol(token)
    except Exception:
        bmp = None

    if bmp:
        btn: wx.Button = wx.BitmapButton(
            parent,
            bitmap=bmp,
            size=(bmp.GetWidth() + 10, bmp.GetHeight() + 10),
            style=wx.BU_EXACTFIT,
        )
    else:
        btn = wx.Button(parent, label=token, size=(44, 28))
        btn.SetFont(get_mana_font(font_size))

    _TOKEN_LABELS = {
        "W": "White",
        "U": "Blue",
        "B": "Black",
        "R": "Red",
        "G": "Green",
        "C": "Colorless",
        "X": "X (variable)",
    }
    btn.SetBackgroundColour(DARK_ALT)
    btn.SetForegroundColour(LIGHT_TEXT)
    btn.SetToolTip(_TOKEN_LABELS.get(token, token))
    btn.Bind(wx.EVT_BUTTON, lambda _evt, sym=token: handler(sym))
    return btn
