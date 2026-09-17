"""Event handlers, buffer renderers, and public state setters for the mana rich-text control."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
import wx.richtext

from utils.constants import (
    MANA_INPUT_CHARS,
    MANA_KEY_SYMBOL_MAP,
    MANA_SYMBOL_PATTERN,
    MANA_TRAILING_SYMBOL_PATTERN,
    NAVIGATION_KEYS,
)
from widgets.panels.mana_rich_text_ctrl.keyboard_evts import key_char

if TYPE_CHECKING:
    from widgets.mana_icon_factory import ManaIconFactory

#: RichTextImage property naming the ``{X}`` symbol an inline image stands for.
MANA_SYMBOL_PROPERTY = "mana_symbol"

_LINE_BREAK_KEYS = frozenset({wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER})


class ManaRichTextInnerHandlersMixin:
    """Event callbacks, buffer rendering, and public state setters for the inner RichTextCtrl."""

    # Attributes supplied by the inner RichTextCtrl's __init__.
    _mana_icons: ManaIconFactory
    _plain_text: str
    _symbol_list: list[str]
    _padded_image_cache: dict[tuple[str, int, tuple[int, int, int]], wx.Image]
    _held_keys: set[str]
    _chord_keys: set[str]
    _mana_mode_active: bool
    _single_line: bool
    _rendering: bool
    _hint_label: wx.StaticText

    # ------------------------------------------------------------------
    # TextCtrl-compatible API (delegated by the Panel wrapper)
    # ------------------------------------------------------------------

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
        self._rendering = True
        self.Freeze()
        try:
            self.Clear()
            self._symbol_list = []
            if self._plain_text:
                self._render_plain_text(self._plain_text)
            self.SetInsertionPointEnd()
        finally:
            self.Thaw()
            self._rendering = False
        self._sync_hint_visibility()

    def _buffer_plain_text(self) -> str:
        """Rebuild the brace-notation value from what the buffer now holds.

        Text runs are read as-is and each symbol image as the ``{X}`` it was
        written for (tagged in :meth:`_write_mana_image`), so the value survives
        edits made anywhere in the box, not just at its end.
        """
        paragraphs: list[str] = []
        for paragraph in self.GetBuffer().GetChildren():
            parts: list[str] = []
            for child in paragraph.GetChildren():
                if isinstance(child, wx.richtext.RichTextImage):
                    parts.append(child.GetProperties().GetPropertyString(MANA_SYMBOL_PROPERTY))
                elif isinstance(child, wx.richtext.RichTextPlainText):
                    parts.append(child.GetText())
            paragraphs.append("".join(parts))
        return "\n".join(paragraphs)

    def _on_buffer_changed(self, evt: wx.CommandEvent) -> None:
        evt.Skip()
        if self._rendering or self.IsBeingDeleted():
            return
        text = self._buffer_plain_text()
        if self._single_line and "\n" in text:
            # A pasted line break: fold it into a space and redraw on one line.
            self._plain_text = text.replace("\n", " ")
            wx.CallAfter(self._rerender_if_alive)
            return
        self._plain_text = text

    def _rerender_if_alive(self) -> None:
        if self:
            self._rerender()

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
        image = self.GetBuffer().GetLeafObjectAtPosition(self.GetInsertionPoint() - 1)
        if isinstance(image, wx.richtext.RichTextImage):
            image.GetProperties().SetProperty(MANA_SYMBOL_PROPERTY, symbol)
        self._symbol_list.append(symbol)

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
        # Other printable keys are swallowed -- the mana-cost box cannot
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

        if self._is_line_break_key(evt):
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
        if self._is_line_break_key(evt):
            return
        if evt.GetKeyCode() == ord("C") and evt.ControlDown() and not evt.ShiftDown():
            self._copy_plain_text()
            return
        evt.Skip()

    def _on_single_line_char(self, evt: wx.KeyEvent) -> None:
        # Backstop for a char event that arrives without its key-down having
        # been refused (wxMSW only suppresses the char when key-down is eaten).
        if self._is_line_break_key(evt):
            return
        evt.Skip()

    def _is_line_break_key(self, evt: wx.KeyEvent) -> bool:
        return self._single_line and evt.GetKeyCode() in _LINE_BREAK_KEYS


class ManaSymbolRichCtrlHandlersMixin:
    """Event callbacks, frame painting, and public state setters for :class:`ManaSymbolRichCtrl`."""

    # Attributes supplied by :class:`ManaSymbolRichCtrl`'s __init__.
    _inner: wx.richtext.RichTextCtrl
    _clip: wx.Panel | None

    # ------------------------------------------------------------------
    # Frame painting + inner layout
    # ------------------------------------------------------------------

    def _layout_inner(self) -> None:
        from widgets.panels.mana_rich_text_ctrl.frame import _BORDER_DIP

        size = self.GetClientSize()
        if size.width <= 0 or size.height <= 0:
            return
        thick = self.FromDIP(_BORDER_DIP)
        width = max(0, size.width - 2 * thick)
        height = max(0, size.height - 2 * thick)
        if self._clip is None:
            self._inner.SetSize(thick, thick, width, height)
            return
        scrollbar = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X, self._inner)
        self._clip.SetSize(thick, thick, width, height)
        self._inner.SetSize(0, 0, width + scrollbar, height)

    def _on_size(self, evt: wx.SizeEvent) -> None:
        evt.Skip()
        self._layout_inner()
        self.Refresh()

    def _on_paint(self, _evt: wx.PaintEvent) -> None:
        """Paint the frame with the app's one input border.

        Phase 6b founded this frame on ``BORDER_SUBTLE`` as an explicit
        placeholder, on the argument that a single control should not decide
        what marks a text input for the whole app while every native
        ``wx.TextCtrl`` beside it had no border at all. Phase 6c answered that
        question -- ``BORDER_STRONG`` at rest, ``FOCUS_RING`` on focus -- so
        this control now calls the same painter every other field does rather
        than keeping a second, quieter idiom of its own. The 2-DIP geometry it
        already had is exactly what that painter expects, so nothing reflows.
        """
        from widgets.input_frame import paint_input_border

        dc = wx.AutoBufferedPaintDC(self)
        paint_input_border(
            self,
            dc,
            enabled=self._inner.IsEnabled(),
            focused=self._inner.HasFocus(),
            editable=self._inner.IsEditable(),
            fill=self._inner.GetBackgroundColour(),
        )

    def _on_inner_focus_change(self, evt: wx.FocusEvent) -> None:
        evt.Skip()
        # Defer: HasFocus() may still reflect the pre-transition state.
        wx.CallAfter(self.Refresh)

    # ------------------------------------------------------------------
    # Public TextCtrl-compatible API (delegation to the inner RTC)
    # ------------------------------------------------------------------

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
