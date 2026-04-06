import wx

from utils.constants import (
    DARK_ACCENT,
    DARK_ALT,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
    SUBDUED_TEXT,
)


def stylize_label(label: wx.StaticText, subtle: bool = False) -> None:
    label.SetForegroundColour(SUBDUED_TEXT if subtle else LIGHT_TEXT)
    label.SetBackgroundColour(DARK_PANEL if subtle else DARK_BG)
    font = label.GetFont()
    if not subtle:
        font.MakeBold()
    label.SetFont(font)


def stylize_textctrl(ctrl: wx.TextCtrl, multiline: bool = False) -> None:
    ctrl.SetBackgroundColour(DARK_ALT)
    ctrl.SetForegroundColour(LIGHT_TEXT)
    font = ctrl.GetFont()
    if multiline:
        font.SetPointSize(font.GetPointSize() + 1)
    ctrl.SetFont(font)


def stylize_choice(ctrl: wx.Choice) -> None:
    ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
    ctrl.SetForegroundColour(wx.Colour(0, 0, 0))


def stylize_listbox(ctrl: wx.ListBox) -> None:
    ctrl.SetBackgroundColour(wx.SystemSettings.GetColour(wx.SYS_COLOUR_BTNFACE))
    ctrl.SetForegroundColour(wx.Colour(0, 0, 0))
    if hasattr(ctrl, "SetSelectionBackground"):
        ctrl.SetSelectionBackground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHT))
        ctrl.SetSelectionForeground(wx.SystemSettings.GetColour(wx.SYS_COLOUR_HIGHLIGHTTEXT))


def stylize_button(button: wx.Button) -> None:
    button.SetBackgroundColour(DARK_ACCENT)
    button.SetForegroundColour(wx.Colour(12, 14, 18))
    font = button.GetFont()
    font.MakeBold()
    button.SetFont(font)
