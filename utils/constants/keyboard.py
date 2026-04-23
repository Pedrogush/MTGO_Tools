"""Keyboard-related constants shared across widgets."""

import wx

NAVIGATION_KEYS: frozenset[int] = frozenset(
    {
        wx.WXK_TAB,
        wx.WXK_LEFT,
        wx.WXK_RIGHT,
        wx.WXK_UP,
        wx.WXK_DOWN,
        wx.WXK_HOME,
        wx.WXK_END,
        wx.WXK_PAGEUP,
        wx.WXK_PAGEDOWN,
        wx.WXK_RETURN,
        wx.WXK_NUMPAD_ENTER,
        wx.WXK_ESCAPE,
        wx.WXK_SHIFT,
        wx.WXK_CONTROL,
        wx.WXK_ALT,
    }
)
