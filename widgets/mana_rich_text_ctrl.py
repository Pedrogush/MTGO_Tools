from __future__ import annotations

import re
from typing import TYPE_CHECKING

import wx
import wx.richtext

from utils.constants import (
    DARK_ALT,
    LIGHT_TEXT,
    MANA_INPUT_CHARS,
    MANA_KEY_SYMBOL_MAP,
    MANA_SYMBOL_PATTERN,
)
from utils.keyboard_evts import key_char

if TYPE_CHECKING:
    from utils.mana_icon_factory import ManaIconFactory


_NAVIGATION_KEYS: frozenset[int] = frozenset({
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
})


class ManaSymbolRichCtrl(wx.richtext.RichTextCtrl):
    def __init__(
        self,
        parent: wx.Window,
        mana_icons: "ManaIconFactory",
        *,
        readonly: bool = False,
        multiline: bool = True,
        mana_key_input: bool = False,
        ctrl_m_mana_mode: bool = False,
    ) -> None:
        style = wx.BORDER_THEME | wx.richtext.RE_MULTILINE
        if readonly:
            style |= wx.richtext.RE_READONLY
        super().__init__(parent, style=style)

        self._mana_icons = mana_icons
        self._plain_text: str = ""
        self._symbol_list: list[str] = []

        self._held_keys: set[str] = set()
        self._sequence_keys: set[str] = set()
        self._mana_mode_active: bool = False

        self._hint: str = ""
        self._showing_hint: bool = False

        self._text_font: wx.Font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        self.SetFont(self._text_font)

        if not multiline:
            ref = wx.TextCtrl(parent)
            ref_h = ref.GetBestSize().height
            ref.Destroy()
            self.SetMinSize(wx.Size(-1, ref_h))

        self.Clear()
        self._apply_dark_style()

        if mana_key_input and not readonly:
            self.Bind(wx.EVT_KEY_DOWN, self._on_mana_key_down)
            self.Bind(wx.EVT_KEY_UP, self._on_mana_key_up)
        elif ctrl_m_mana_mode and not readonly:
            self.Bind(wx.EVT_KEY_DOWN, self._on_ctrl_m_key_down)
            self.Bind(wx.EVT_KEY_UP, self._on_ctrl_m_key_up)
        else:
            self.Bind(wx.EVT_KEY_DOWN, self._on_copy_key_down)

        self.Bind(wx.EVT_SET_FOCUS, self._on_focus_gained)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_focus_lost)

    def GetValue(self) -> str:  # type: ignore[override]
        return self._plain_text

    def ChangeValue(self, text: str) -> None:  # type: ignore[override]
        self._plain_text = text
        self._rerender()

    def SetValue(self, text: str) -> None:  # type: ignore[override]
        self._plain_text = text
        self._rerender()
        self._emit_text_event()

    def SetHint(self, hint: str) -> None:  # type: ignore[override]
        self._hint = hint
        if not self._plain_text and not self.HasFocus():
            self._show_hint()

    def _show_hint(self) -> None:
        if not self._hint or self._showing_hint:
            return
        self._showing_hint = True
        self.Freeze()
        try:
            self.Clear()
            self._apply_hint_style()
            self.WriteText(self._hint)
            self.SetInsertionPoint(0)
        finally:
            self.Thaw()

    def _hide_hint(self) -> None:
        if self._showing_hint:
            self._rerender()

    def _on_focus_gained(self, evt: wx.FocusEvent) -> None:
        self._hide_hint()
        evt.Skip()

    def _on_focus_lost(self, evt: wx.FocusEvent) -> None:
        if not self._plain_text:
            self._show_hint()
        evt.Skip()

    def _left_indent_mm10(self) -> int:
        dpi_x = self.FromDIP(96)
        return round(2 * 254 / dpi_x) if dpi_x > 0 else 0

    def _apply_hint_style(self) -> None:
        attr = wx.richtext.RichTextAttr()
        attr.SetFont(self._text_font)
        attr.SetTextColour(wx.Colour(87, 87, 87))
        attr.SetBackgroundColour(DARK_ALT)
        attr.SetLeftIndent(self._left_indent_mm10())
        self.SetDefaultStyle(attr)
        self.SetBasicStyle(attr)

    def _apply_dark_style(self) -> None:
        self.SetBackgroundColour(DARK_ALT)
        attr = wx.richtext.RichTextAttr()
        attr.SetFont(self._text_font)
        attr.SetTextColour(LIGHT_TEXT)
        attr.SetBackgroundColour(DARK_ALT)
        attr.SetLeftIndent(self._left_indent_mm10())
        self.SetDefaultStyle(attr)
        self.SetBasicStyle(attr)

    def _rerender(self) -> None:
        self._showing_hint = False
        self.Freeze()
        try:
            self.Clear()
            self._apply_dark_style()
            self._symbol_list = []
            if self._plain_text:
                self._render_text(self._plain_text)
            self.SetInsertionPointEnd()
        finally:
            self.Thaw()

    def _render_text(self, text: str) -> None:
        pos = 0
        for m in MANA_SYMBOL_PATTERN.finditer(text):
            if m.start() > pos:
                self.WriteText(text[pos : m.start()])
            self._write_mana_image(m.group())
            pos = m.end()
        if pos < len(text):
            self.WriteText(text[pos:])

    def _write_mana_image(self, symbol: str) -> None:
        token = symbol[1:-1] if len(symbol) > 2 else symbol
        bmp = self._mana_icons.bitmap_for_symbol_hires(token)
        if bmp and bmp.IsOk():
            sym_h = self._symbol_height()
            img = bmp.ConvertToImage()
            if img.GetHeight() != sym_h:
                img = img.Scale(sym_h, sym_h, wx.IMAGE_QUALITY_HIGH)
            line_h = self.GetCharHeight()
            pad_top = max(0, (line_h - sym_h) // 2) + 3
            image_h = max(line_h, sym_h + pad_top)
            bg = self.GetBackgroundColour()
            padded = wx.Image(sym_h, image_h)
            padded.SetRGB(wx.Rect(0, 0, sym_h, image_h), bg.Red(), bg.Green(), bg.Blue())
            padded.Paste(img, 0, pad_top)
            img = padded
            self.WriteImage(img)
            self._symbol_list.append(symbol)
        else:
            self.WriteText(symbol)

    def _symbol_height(self) -> int:
        ch = self.GetCharHeight()
        return max(16, ch - 2)

    def _emit_text_event(self) -> None:
        evt = wx.CommandEvent(wx.wxEVT_TEXT, self.GetId())
        evt.SetString(self._plain_text)
        evt.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(evt)

    def _on_mana_key_down(self, evt: wx.KeyEvent) -> None:
        kc = evt.GetKeyCode()

        if kc == wx.WXK_BACK:
            if self._plain_text:
                m = re.search(r"\{[^}]+\}$", self._plain_text)
                if m:
                    self._plain_text = self._plain_text[: m.start()]
                else:
                    self._plain_text = self._plain_text[:-1]
                self._rerender()
                self._emit_text_event()
            return

        if kc == wx.WXK_DELETE:
            self._plain_text = ""
            self._rerender()
            self._emit_text_event()
            return

        if evt.ControlDown():
            if kc == ord("C") and not evt.ShiftDown():
                self._copy_plain_text()
                return
            evt.Skip()
            return

        if kc in _NAVIGATION_KEYS:
            evt.Skip()
            return

        ch = key_char(evt)
        if ch and ch in MANA_INPUT_CHARS:
            self._held_keys.add(ch)
            self._sequence_keys.add(ch)
            return

    def _on_mana_key_up(self, evt: wx.KeyEvent) -> None:
        ch = key_char(evt)
        if ch:
            self._held_keys.discard(ch)

        if not self._held_keys and self._sequence_keys:
            seq = frozenset(self._sequence_keys)
            self._sequence_keys.clear()
            symbol = MANA_KEY_SYMBOL_MAP.get(seq)
            if symbol:
                self._plain_text += f"{{{symbol}}}"
                self._rerender()
                self._emit_text_event()

        evt.Skip()

    def _on_ctrl_m_key_down(self, evt: wx.KeyEvent) -> None:
        kc = evt.GetKeyCode()
        if kc == ord("M") and evt.ControlDown():
            self._mana_mode_active = not self._mana_mode_active
            self._held_keys.clear()
            self._sequence_keys.clear()
            return

        if self._mana_mode_active:
            self._on_mana_key_down(evt)
            return

        if kc == ord("C") and evt.ControlDown() and not evt.ShiftDown():
            self._copy_plain_text()
            return

        evt.Skip()

    def _on_ctrl_m_key_up(self, evt: wx.KeyEvent) -> None:
        if self._mana_mode_active:
            self._on_mana_key_up(evt)
            return
        evt.Skip()

    def _on_copy_key_down(self, evt: wx.KeyEvent) -> None:
        if evt.GetKeyCode() == ord("C") and evt.ControlDown() and not evt.ShiftDown():
            self._copy_plain_text()
            return
        evt.Skip()

    def _copy_plain_text(self) -> None:
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self._plain_text))
            wx.TheClipboard.Close()
