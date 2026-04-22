"""Mana-symbol-aware RichTextCtrl used by mana-cost and oracle-text fields.

Renders `{W}`, `{R/G}`, `{2/W}` etc. as inline images while keeping the
brace-notation string as the canonical value returned by `GetValue()`.

Input modes (mutually exclusive):
  mana_key_input    — every keystroke is intercepted; single letters and
                      two-key chords resolve to mana symbols (mana-cost box).
  ctrl_m_mana_mode  — typing behaves like a regular text field until the user
                      presses Ctrl+M, which toggles the mana_key_input flow
                      on/off (oracle-text search: mostly words, occasional
                      symbols).
Passing neither yields a plain display control with Ctrl+C → plain text.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
import wx.richtext

from utils.constants import (
    DARK_ALT,
    HINT_TEXT,
    LIGHT_TEXT,
    MANA_INPUT_CHARS,
    MANA_KEY_SYMBOL_MAP,
    MANA_SYMBOL_PATTERN,
    MANA_TRAILING_SYMBOL_PATTERN,
    NAVIGATION_KEYS,
)
from utils.keyboard_evts import key_char

if TYPE_CHECKING:
    from utils.mana_icon_factory import ManaIconFactory


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
        self._padded_image_cache: dict[tuple[str, int, tuple[int, int, int]], wx.Image] = {}

        # _held_keys is idempotent under key auto-repeat (set membership);
        # _sequence_keys accumulates across the whole chord so a key released
        # before its partner still contributes to the final symbol.
        self._held_keys: set[str] = set()
        self._sequence_keys: set[str] = set()
        self._mana_mode_active: bool = False

        self._hint: str = ""
        self._showing_hint: bool = False

        self.SetFont(wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT))

        if not multiline:
            ref = wx.TextCtrl(parent)
            ref_h = ref.GetBestSize().height
            ref.Destroy()
            self.SetMinSize(wx.Size(-1, ref_h))

        self.Clear()
        self._apply_default_style()

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
            self._apply_default_style()
            start = self.GetInsertionPoint()
            self.WriteText(self._hint)
            end = self.GetInsertionPoint()
            hint_attr = wx.richtext.RichTextAttr()
            hint_attr.SetTextColour(wx.Colour(*HINT_TEXT))
            hint_attr.SetBackgroundColour(DARK_ALT)
            self.SetStyle(wx.richtext.RichTextRange(start, end), hint_attr)
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

    def _apply_default_style(self) -> None:
        """Install the sole persistent style (light text on DARK_ALT).

        Hint text gets its grey colour from an inline BeginStyle/EndStyle
        wrapper around WriteText; the basic/default style stays dark so
        typed characters never inherit the hint colour.
        """
        self.SetBackgroundColour(DARK_ALT)
        attr = wx.richtext.RichTextAttr()
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
            self._apply_default_style()
            self._symbol_list = []
            if self._plain_text:
                self._render_text(self._plain_text)
            self.SetInsertionPointEnd()
            # Re-assert the default style after positioning the caret.
            # wxRichTextCtrl's default-typing handler picks the character
            # attributes at the current cursor position; without this the
            # first inserted character can inherit whatever run style was
            # at position 0 before Clear (notably the hint grey).
            self._apply_default_style()
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
        sym_h = self._symbol_height()
        bg = self.GetBackgroundColour()
        cache_key = (token, sym_h, (bg.Red(), bg.Green(), bg.Blue()))

        img = self._padded_image_cache.get(cache_key)
        if img is None:
            bmp = self._mana_icons.bitmap_for_symbol_hires(token)
            if not bmp or not bmp.IsOk():
                self.WriteText(symbol)
                return
            src = bmp.ConvertToImage()
            if src.GetHeight() != sym_h:
                src = src.Scale(sym_h, sym_h, wx.IMAGE_QUALITY_HIGH)
            line_h = self.GetCharHeight()
            pad_top = max(0, (line_h - sym_h) // 2) + 3
            image_h = max(line_h, sym_h + pad_top)
            img = wx.Image(sym_h, image_h)
            img.SetRGB(wx.Rect(0, 0, sym_h, image_h), bg.Red(), bg.Green(), bg.Blue())
            img.Paste(src, 0, pad_top)
            self._padded_image_cache[cache_key] = img

        self.WriteImage(img)
        self._symbol_list.append(symbol)

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
                m = MANA_TRAILING_SYMBOL_PATTERN.search(self._plain_text)
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

        if kc in NAVIGATION_KEYS:
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
