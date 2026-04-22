"""Mana-symbol-aware RichTextCtrl with inline mana-symbol images.

A TextCtrl-compatible control that renders `{W}`, `{R/G}`, `{2/W}` etc.
as inline images while keeping the brace-notation string as the
canonical value returned by `GetValue()`.

The placeholder hint is a separate `wx.StaticText` overlay rather than
text written into the rich-text buffer. Writing the hint into the buffer
(with a grey character style) leaves residue that contaminates later
typed characters — the overlay approach keeps the buffer's style
pristine so typed text always renders in the single persistent dark
style set once in __init__.

Input modes (mutually exclusive, optional):
  mana_key_input    — every key is captured; single letters and two-key
                      chords resolve to mana symbols (mana-cost box).
  ctrl_m_mana_mode  — regular text entry until Ctrl+M toggles into the
                      mana_key_input flow (oracle-text search).

Without either flag the control is a read-through display whose Ctrl+C
copies the canonical plain-text value rather than the RTF placeholder.
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
        mana_icons: ManaIconFactory,
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

        # _held_keys: idempotent under key auto-repeat; _chord_keys:
        # accumulates across the whole chord so a key released before its
        # partner still contributes to the final symbol.
        self._held_keys: set[str] = set()
        self._chord_keys: set[str] = set()
        self._mana_mode_active = False

        font = wx.SystemSettings.GetFont(wx.SYS_DEFAULT_GUI_FONT)
        self.SetFont(font)
        self.SetBackgroundColour(wx.Colour(*DARK_ALT))

        # Install the sole persistent buffer style. Never mutated again,
        # so nothing the control ever writes can leak a foreign colour
        # onto typed characters.
        persistent_style = wx.richtext.RichTextAttr()
        persistent_style.SetTextColour(wx.Colour(*LIGHT_TEXT))
        persistent_style.SetBackgroundColour(wx.Colour(*DARK_ALT))
        self.SetBasicStyle(persistent_style)
        self.SetDefaultStyle(persistent_style)

        if not multiline:
            ref = wx.TextCtrl(parent)
            ref_h = ref.GetBestSize().height
            ref.Destroy()
            self.SetMinSize(wx.Size(-1, ref_h))

        # Hint overlay. Positioned over the rich-text area, never written
        # into the buffer. We leave auto-resize on so SetLabel expands the
        # control to fit the text, and skip SetBackgroundColour (some
        # backends ignore it on StaticText — the RTC's own DARK_ALT bg
        # shows through instead).
        self._hint_label = wx.StaticText(self, label="")
        self._hint_label.SetFont(font)
        self._hint_label.SetForegroundColour(wx.Colour(*HINT_TEXT))
        self._hint_label.Hide()
        self._hint_label.Bind(wx.EVT_LEFT_DOWN, self._on_hint_click)

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
        # The control frequently has no size yet when SetHint is called
        # (parent sizer has not laid out). Re-sync on every size event so
        # the first real layout pass shows the hint.
        self.Bind(wx.EVT_SIZE, self._on_size)

    # ------------------------------------------------------------------
    # Public TextCtrl-compatible API
    # ------------------------------------------------------------------

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
        self._hint_label.SetLabel(hint)
        # Defer to after the current event cycle so focus races and the
        # initial layout pass have a chance to settle before we decide
        # whether to show.
        wx.CallAfter(self._sync_hint_visibility)

    # ------------------------------------------------------------------
    # Hint overlay management
    # ------------------------------------------------------------------

    def _has_content(self) -> bool:
        # Covers both mana-mode symbols (tracked in _plain_text) and any
        # native typing that lands in the RichTextCtrl buffer directly
        # (ctrl_m mode when not in mana mode).
        return bool(self._plain_text) or self.GetLastPosition() > 0

    def _sync_hint_visibility(self) -> None:
        show = bool(self._hint_label.GetLabel()) and not self._has_content() and not self.HasFocus()
        if show:
            inset = wx.Point(self.FromDIP(3), self.FromDIP(2))
            self._hint_label.SetPosition(inset)
            self._hint_label.Show()
            self._hint_label.Raise()
        else:
            self._hint_label.Hide()

    def _on_hint_click(self, _evt: wx.MouseEvent) -> None:
        # Forward the click-to-focus intent; StaticText does not receive
        # keyboard focus on its own.
        self.SetFocus()

    def _on_focus_gained(self, evt: wx.FocusEvent) -> None:
        self._hint_label.Hide()
        evt.Skip()

    def _on_focus_lost(self, evt: wx.FocusEvent) -> None:
        evt.Skip()
        # HasFocus() may still reflect the pre-transfer state during the
        # EVT_KILL_FOCUS callback; defer so the check sees reality.
        wx.CallAfter(self._sync_hint_visibility)

    def _on_size(self, evt: wx.SizeEvent) -> None:
        evt.Skip()
        self._sync_hint_visibility()

    # ------------------------------------------------------------------
    # Buffer rendering
    # ------------------------------------------------------------------

    def _rerender(self) -> None:
        self.Freeze()
        try:
            self.Clear()
            self._symbol_list = []
            if self._plain_text:
                self._render_plain_text(self._plain_text)
            self.SetInsertionPointEnd()
        finally:
            self.Thaw()
        self._sync_hint_visibility()

    def _render_plain_text(self, text: str) -> None:
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
        return max(16, self.GetCharHeight() - 2)

    def _emit_text_event(self) -> None:
        evt = wx.CommandEvent(wx.wxEVT_TEXT, self.GetId())
        evt.SetString(self._plain_text)
        evt.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(evt)

    def _copy_plain_text(self) -> None:
        if wx.TheClipboard.Open():
            wx.TheClipboard.SetData(wx.TextDataObject(self._plain_text))
            wx.TheClipboard.Close()

    # ------------------------------------------------------------------
    # Key handling
    # ------------------------------------------------------------------

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
            if self._plain_text:
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
            self._chord_keys.add(ch)
            return
        # Any other printable key is swallowed — a mana-cost box cannot
        # hold arbitrary text.

    def _on_mana_key_up(self, evt: wx.KeyEvent) -> None:
        ch = key_char(evt)
        if ch:
            self._held_keys.discard(ch)

        if not self._held_keys and self._chord_keys:
            chord = frozenset(self._chord_keys)
            self._chord_keys.clear()
            symbol = MANA_KEY_SYMBOL_MAP.get(chord)
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
            self._chord_keys.clear()
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
