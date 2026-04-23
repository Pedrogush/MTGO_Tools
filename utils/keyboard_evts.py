from __future__ import annotations

import wx


def key_char(evt: wx.KeyEvent) -> str | None:
    uni = evt.GetUnicodeKey()
    if uni and uni != wx.WXK_NONE:
        c = chr(uni)
        if c.isalnum():
            return c.lower()
    kc = evt.GetKeyCode()
    if wx.WXK_NUMPAD0 <= kc <= wx.WXK_NUMPAD9:
        return str(kc - wx.WXK_NUMPAD0)
    return None
