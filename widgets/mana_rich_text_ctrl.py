"""Mana-symbol-aware TextCtrl-compatible widget with inline mana-symbol images.

Renders `{W}`, `{R/G}`, `{2/W}` etc. as inline images while keeping the
brace-notation string as the canonical value returned by `GetValue()`.

Why this is a wx.Panel, not a wx.richtext.RichTextCtrl: the native
TextCtrl's blue focus underline is painted by Windows' uxtheme on the
EDIT control's non-client area, which a custom-drawn RichTextCtrl can't
receive. To match the look we paint the whole 2-DIP grey frame ourselves
— replicating the outer/inner two-tone composition sampled from an
adjacent native wx.TextCtrl — and tint the bottom outer row DARK_ACCENT
on focus. The actual rich-text buffer is a borderless child RichTextCtrl
that fills the panel interior.

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
    DARK_ACCENT,
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


# Three-tone frame matching the native Win11 dark-mode TextCtrl outline,
# as sampled from an adjacent wx.TextCtrl in the same dialog: a 1-DIP
# outer halo (lighter on top/left/right, darker on bottom) wrapping a
# 1-DIP near-white inner ring. Total frame thickness: 2 DIP on every
# side. On focus the bottom outer row tints the accent colour.
_BORDER_OUTER_LIGHT = wx.Colour(236, 236, 236)
_BORDER_INNER = wx.Colour(254, 254, 254)
_BORDER_OUTER_DARK = wx.Colour(131, 131, 131)
_BORDER_DIP = 2
_BORDER_OUTER_DIP = 1


class _ManaRichTextInner(wx.richtext.RichTextCtrl):
    """Inner borderless RichTextCtrl owned by ManaSymbolRichCtrl.

    Handles buffer rendering, symbol images, the hint overlay, and all
    key interception. The surrounding frame is painted by the parent
    Panel, not here.
    """

    def __init__(
        self,
        parent: wx.Window,
        mana_icons: ManaIconFactory,
        *,
        readonly: bool,
        mana_key_input: bool,
        ctrl_m_mana_mode: bool,
    ) -> None:
        style = wx.BORDER_NONE | wx.richtext.RE_MULTILINE
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

        # Hint overlay (a StaticText child, not text in the buffer).
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
        self.Bind(wx.EVT_SIZE, self._on_size)

    # ------------------------------------------------------------------
    # TextCtrl-compatible API (delegated by the Panel wrapper)
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
        self.SetFocus()

    def _on_focus_gained(self, evt: wx.FocusEvent) -> None:
        evt.Skip()
        self._sync_hint_visibility()

    def _on_focus_lost(self, evt: wx.FocusEvent) -> None:
        evt.Skip()
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
        # Other printable keys are swallowed — the mana-cost box cannot
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


class ManaSymbolRichCtrl(wx.Panel):
    """Public wrapper. Custom-paints a 2-DIP frame matching the native Win11
    dark-mode wx.TextCtrl outline (outer light halo + inner near-white
    ring, with a darker outer row at the bottom that tints DARK_ACCENT on
    focus); delegates the TextCtrl API to an inner borderless RichTextCtrl
    that fills the panel interior.
    """

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
        super().__init__(parent, style=wx.BORDER_NONE)
        # Required by wx.AutoBufferedPaintDC: we paint the background
        # ourselves in _on_paint, so suppress the default erase-bg pass.
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetBackgroundColour(_BORDER_OUTER_LIGHT)

        self._inner = _ManaRichTextInner(
            self,
            mana_icons,
            readonly=readonly,
            mana_key_input=mana_key_input,
            ctrl_m_mana_mode=ctrl_m_mana_mode,
        )

        if not multiline:
            ref = wx.TextCtrl(parent)
            ref_h = ref.GetBestSize().height
            ref.Destroy()
            self.SetMinSize(wx.Size(-1, ref_h))

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        # Inner focus changes drive a re-paint so the bottom edge tints.
        self._inner.Bind(wx.EVT_SET_FOCUS, self._on_inner_focus_change)
        self._inner.Bind(wx.EVT_KILL_FOCUS, self._on_inner_focus_change)

        self._layout_inner()

    # ------------------------------------------------------------------
    # Frame painting + inner layout
    # ------------------------------------------------------------------

    def _layout_inner(self) -> None:
        size = self.GetClientSize()
        if size.width <= 0 or size.height <= 0:
            return
        thick = self.FromDIP(_BORDER_DIP)
        self._inner.SetSize(
            thick,
            thick,
            max(0, size.width - 2 * thick),
            max(0, size.height - 2 * thick),
        )

    def _on_size(self, evt: wx.SizeEvent) -> None:
        evt.Skip()
        self._layout_inner()
        self.Refresh()

    def _on_paint(self, _evt: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        size = self.GetClientSize()
        outer = self.FromDIP(_BORDER_OUTER_DIP)

        dc.SetPen(wx.TRANSPARENT_PEN)
        # Outer halo covers the whole rectangle; the inner ring and the
        # bottom outer row are painted over it. The inner RTC occupies
        # the centre.
        dc.SetBrush(wx.Brush(_BORDER_OUTER_LIGHT))
        dc.DrawRectangle(0, 0, size.width, size.height)

        # Near-white inner ring inset by the outer halo.
        dc.SetBrush(wx.Brush(_BORDER_INNER))
        dc.DrawRectangle(
            outer,
            outer,
            max(0, size.width - 2 * outer),
            max(0, size.height - 2 * outer),
        )

        # Full bottom band tints DARK_ACCENT on focus.
        bottom_colour = wx.Colour(*DARK_ACCENT) if self._inner.HasFocus() else _BORDER_OUTER_DARK
        dc.SetBrush(wx.Brush(bottom_colour))
        dc.DrawRectangle(0, size.height - 2 * outer, size.width, 2 * outer)

    def _on_inner_focus_change(self, evt: wx.FocusEvent) -> None:
        evt.Skip()
        # Defer: HasFocus() may still reflect the pre-transition state.
        wx.CallAfter(self.Refresh)

    # ------------------------------------------------------------------
    # Public TextCtrl-compatible API (delegation to the inner RTC)
    # ------------------------------------------------------------------

    def GetValue(self) -> str:
        return self._inner.GetValue()

    def SetValue(self, text: str) -> None:
        self._inner.SetValue(text)

    def ChangeValue(self, text: str) -> None:
        self._inner.ChangeValue(text)

    def SetHint(self, hint: str) -> None:
        self._inner.SetHint(hint)

    def SetToolTip(self, tip) -> None:  # type: ignore[override]
        # The inner RTC covers the whole interior; putting the tooltip on
        # the frame panel alone would only fire on the 1-DIP edge.
        self._inner.SetToolTip(tip)
