"""Mana-symbol-aware RichTextCtrl.

Renders {W}, {R/G}, {2/W} etc. as inline images inside a RichTextCtrl.
Maintains a plain-text canonical value so GetValue() always returns the
underlying text (e.g. '{W}{U}') regardless of what images are displayed.

Two specialised modes are available via constructor flags:
  mana_key_input=True    – intercept letter/digit key combos and append the
                           corresponding mana symbol (for the mana-cost search).
  oracle_symbol_detect=True – detect {X} patterns as the user types and replace
                              them with rendered images (for oracle-text fields).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import wx
import wx.richtext

from utils.constants import DARK_ALT, LIGHT_TEXT, SUBDUED_TEXT

if TYPE_CHECKING:
    from utils.mana_icon_factory import ManaIconFactory

# ---------------------------------------------------------------------------
# Mana symbol pattern
# ---------------------------------------------------------------------------

_SYMBOL_PATTERN = re.compile(r"\{[^}]{1,6}\}")

# ---------------------------------------------------------------------------
# Keyboard shortcut → symbol map
# frozenset of lowercase key chars → token (without braces)
# ---------------------------------------------------------------------------

_SINGLE = {
    "w": "W",
    "u": "U",
    "b": "B",
    "r": "R",
    "g": "G",
    "c": "C",
    "s": "S",
    "x": "X",
    "y": "Y",
    "z": "Z",
}
_HYBRID: dict[tuple[str, str], str] = {
    ("w", "u"): "W/U",
    ("w", "b"): "W/B",
    ("u", "b"): "U/B",
    ("u", "r"): "U/R",
    ("b", "r"): "B/R",
    ("b", "g"): "B/G",
    ("r", "g"): "R/G",
    ("r", "w"): "R/W",
    ("g", "w"): "G/W",
    ("g", "u"): "G/U",
    ("c", "w"): "C/W",
    ("c", "u"): "C/U",
    ("c", "b"): "C/B",
    ("c", "r"): "C/R",
    ("c", "g"): "C/G",
    ("2", "w"): "2/W",
    ("2", "u"): "2/U",
    ("2", "b"): "2/B",
    ("2", "r"): "2/R",
    ("2", "g"): "2/G",
    ("w", "p"): "W/P",
    ("u", "p"): "U/P",
    ("b", "p"): "B/P",
    ("r", "p"): "R/P",
    ("g", "p"): "G/P",
}

_KEY_SYMBOL_MAP: dict[frozenset[str], str] = {}
for _k, _v in _SINGLE.items():
    _KEY_SYMBOL_MAP[frozenset({_k})] = _v
for (_a, _b), _v in _HYBRID.items():
    _KEY_SYMBOL_MAP[frozenset({_a, _b})] = _v
for _i in range(10):
    _KEY_SYMBOL_MAP[frozenset({str(_i)})] = str(_i)

_MANA_INPUT_CHARS: set[str] = set("wubrgcsxyz0123456789p")


def _key_char(evt: wx.KeyEvent) -> str | None:
    """Return the lowercase character for a key event, or None."""
    uni = evt.GetUnicodeKey()
    if uni and uni != wx.WXK_NONE:
        c = chr(uni)
        if c.isalnum():
            return c.lower()
    kc = evt.GetKeyCode()
    if wx.WXK_NUMPAD0 <= kc <= wx.WXK_NUMPAD9:
        return str(kc - wx.WXK_NUMPAD0)
    return None


# ---------------------------------------------------------------------------
# Main widget
# ---------------------------------------------------------------------------


class ManaSymbolRichCtrl(wx.richtext.RichTextCtrl):
    """RichTextCtrl that renders mana symbols {W}, {R/G} etc. as inline images.

    The canonical text (with brace-notation symbols) is stored in _plain_text.
    GetValue() always returns _plain_text; ChangeValue() / SetValue() trigger
    a full re-render from _plain_text.

    When *mana_key_input* is True all printable key events are intercepted;
    single letters/digits and their two-key combinations produce the matching
    mana symbol upon key-release.

    When *oracle_symbol_detect* is True the control scans the typed text for
    complete {X} patterns after each key-up and after paste events, replacing
    them with rendered images.
    """

    def __init__(
        self,
        parent: wx.Window,
        mana_icons: "ManaIconFactory",
        *,
        readonly: bool = False,
        multiline: bool = True,
        mana_key_input: bool = False,
        oracle_symbol_detect: bool = False,
    ) -> None:
        style = wx.BORDER_NONE
        if multiline:
            style |= wx.richtext.RE_MULTILINE
        if readonly:
            style |= wx.richtext.RE_READONLY
        super().__init__(parent, style=style)

        self._mana_icons = mana_icons
        self._plain_text: str = ""
        self._symbol_list: list[str] = []  # per-image symbol tokens, insertion order
        self._suppress: int = 0
        self._readonly = readonly
        self._mana_key_input = mana_key_input
        self._oracle_symbol_detect = oracle_symbol_detect

        # mana key-input state
        self._held_keys: set[str] = set()
        self._sequence_keys: set[str] = set()

        self._apply_dark_style()

        # --- event bindings ---
        if mana_key_input and not readonly:
            self.Bind(wx.EVT_KEY_DOWN, self._on_mana_key_down)
            self.Bind(wx.EVT_KEY_UP, self._on_mana_key_up)
        elif oracle_symbol_detect and not readonly:
            self.Bind(wx.EVT_KEY_UP, self._on_oracle_key_up)
            self.Bind(wx.EVT_KEY_DOWN, self._on_oracle_key_down_for_paste)

        # intercept Ctrl+C to put plain text (not RTF) on clipboard
        self.Bind(wx.EVT_KEY_DOWN, self._on_copy_key_down)

    # ------------------------------------------------------------------
    # Public TextCtrl-compatible API
    # ------------------------------------------------------------------

    def GetValue(self) -> str:  # type: ignore[override]
        return self._plain_text

    def ChangeValue(self, text: str) -> None:  # type: ignore[override]
        """Set text without emitting EVT_TEXT (matches wx.TextCtrl behaviour)."""
        self._plain_text = text
        self._rerender()

    def SetValue(self, text: str) -> None:  # type: ignore[override]
        """Set text and emit EVT_TEXT (matches wx.TextCtrl behaviour)."""
        self._plain_text = text
        self._rerender()
        self._emit_text_event()

    def SetHint(self, hint: str) -> None:  # type: ignore[override]
        """Store hint for future use (displayed as tooltip if not natively supported)."""
        self.SetToolTip(hint)

    # ------------------------------------------------------------------
    # Internal rendering
    # ------------------------------------------------------------------

    def _apply_dark_style(self) -> None:
        self.SetBackgroundColour(DARK_ALT)
        attr = wx.richtext.RichTextAttr()
        attr.SetTextColour(LIGHT_TEXT)
        attr.SetBackgroundColour(DARK_ALT)
        self.SetDefaultStyle(attr)

    def _rerender(self) -> None:
        """Clear and re-render _plain_text."""
        self._suppress += 1
        self.Freeze()
        try:
            self.Clear()
            self._symbol_list = []
            if self._plain_text:
                self._render_text(self._plain_text)
            self.SetInsertionPointEnd()
        finally:
            self._suppress -= 1
            self.Thaw()

    def _render_text(self, text: str) -> None:
        pos = 0
        for m in _SYMBOL_PATTERN.finditer(text):
            if m.start() > pos:
                self.WriteText(text[pos : m.start()])
            self._write_mana_image(m.group())
            pos = m.end()
        if pos < len(text):
            self.WriteText(text[pos:])

    def _write_mana_image(self, symbol: str) -> None:
        """Render a single mana symbol as an inline image."""
        token = symbol[1:-1] if len(symbol) > 2 else symbol
        bmp = self._mana_icons.bitmap_for_symbol(token)
        if bmp and bmp.IsOk():
            h = self._symbol_height()
            img = bmp.ConvertToImage()
            if img.GetHeight() != h:
                img = img.Scale(h, h, wx.IMAGE_QUALITY_HIGH)
            self.WriteImage(img)
            self._symbol_list.append(symbol)
        else:
            self.WriteText(symbol)

    def _symbol_height(self) -> int:
        font = self.GetFont()
        if font.IsOk():
            return max(16, int(font.GetPointSize() * 1.6))
        return 20

    def _emit_text_event(self) -> None:
        evt = wx.CommandEvent(wx.wxEVT_TEXT, self.GetId())
        evt.SetString(self._plain_text)
        evt.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(evt)

    def _reconstruct_from_richtext(self) -> str:
        """Reconstruct _plain_text by mapping \\ufffc image placeholders to symbols.

        wx.richtext.RichTextCtrl.GetValue() returns U+FFFC (Object Replacement
        Character) for each embedded image.  We replace those in order with the
        symbols stored in _symbol_list.
        """
        try:
            raw = super().GetValue()
        except Exception:
            return self._plain_text
        result: list[str] = []
        idx = 0
        for ch in raw:
            if ch == "\ufffc":
                result.append(self._symbol_list[idx] if idx < len(self._symbol_list) else "")
                idx += 1
            else:
                result.append(ch)
        return "".join(result)

    # ------------------------------------------------------------------
    # Mana cost key-input handlers
    # ------------------------------------------------------------------

    def _on_mana_key_down(self, evt: wx.KeyEvent) -> None:
        kc = evt.GetKeyCode()

        # Backspace: remove last symbol or last character
        if kc == wx.WXK_BACK:
            if self._plain_text:
                m = re.search(r"\{[^}]+\}$", self._plain_text)
                if m:
                    self._plain_text = self._plain_text[: m.start()]
                else:
                    self._plain_text = self._plain_text[:-1]
                self._rerender()
                self._emit_text_event()
            return  # consume

        # Delete: clear all
        if kc == wx.WXK_DELETE:
            self._plain_text = ""
            self._rerender()
            self._emit_text_event()
            return  # consume

        # Let ctrl combos through (copy, select-all, etc.)
        if evt.ControlDown():
            evt.Skip()
            return

        # Track mana-relevant keys; consume the event so the char is not
        # written to the RichText buffer directly.
        ch = _key_char(evt)
        if ch and ch in _MANA_INPUT_CHARS:
            self._held_keys.add(ch)
            self._sequence_keys.add(ch)
            return  # consume

        # All other keys: ignore
        return  # consume (mana cost box only accepts mana symbols)

    def _on_mana_key_up(self, evt: wx.KeyEvent) -> None:
        ch = _key_char(evt)
        if ch:
            self._held_keys.discard(ch)

        # When all tracked keys have been released, resolve the symbol.
        if not self._held_keys and self._sequence_keys:
            seq = frozenset(self._sequence_keys)
            self._sequence_keys.clear()
            symbol = _KEY_SYMBOL_MAP.get(seq)
            if symbol:
                self._plain_text += f"{{{symbol}}}"
                self._rerender()
                self._emit_text_event()

        evt.Skip()

    # ------------------------------------------------------------------
    # Oracle-text symbol-detection handlers
    # ------------------------------------------------------------------

    def _on_oracle_key_up(self, evt: wx.KeyEvent) -> None:
        if self._suppress:
            evt.Skip()
            return

        kc = evt.GetKeyCode()
        uni = evt.GetUnicodeKey()
        ch = chr(uni) if (uni and uni != wx.WXK_NONE) else ""

        # Sync plain text from current rich text state
        self._plain_text = self._reconstruct_from_richtext()

        # Decide whether to attempt symbol detection
        trigger = kc == ord("}") or kc == ord("{") or (ch.isalpha() and ch.isupper())
        if trigger:
            new_text = _normalize_symbol_patterns(self._plain_text)
            if new_text != self._plain_text:
                self._plain_text = new_text
                self._rerender()
                self._emit_text_event()
                evt.Skip()
                return

        # For non-trigger keys just keep plain text synced; native EVT_TEXT
        # will propagate normally from the RichText buffer.
        evt.Skip()

    def _on_oracle_key_down_for_paste(self, evt: wx.KeyEvent) -> None:
        """Intercept Ctrl+V to process symbols after paste."""
        if evt.GetKeyCode() == ord("V") and evt.ControlDown():
            evt.Skip()  # let the paste happen
            wx.CallAfter(self._post_paste)
            return
        evt.Skip()

    def _post_paste(self) -> None:
        if not self:
            return
        self._plain_text = self._reconstruct_from_richtext()
        new_text = _normalize_symbol_patterns(self._plain_text)
        if new_text != self._plain_text:
            self._plain_text = new_text
            self._rerender()
        self._emit_text_event()

    # ------------------------------------------------------------------
    # Copy as plain text
    # ------------------------------------------------------------------

    def _on_copy_key_down(self, evt: wx.KeyEvent) -> None:
        if evt.GetKeyCode() == ord("C") and evt.ControlDown() and not evt.ShiftDown():
            if wx.TheClipboard.Open():
                wx.TheClipboard.SetData(wx.TextDataObject(self._plain_text))
                wx.TheClipboard.Close()
            return  # consume; don't propagate
        evt.Skip()


# ---------------------------------------------------------------------------
# Helper: normalise / detect symbol patterns in plain text
# ---------------------------------------------------------------------------


def _normalize_symbol_patterns(text: str) -> str:
    """Uppercase the content inside braces to produce canonical symbol notation."""

    def _upper(m: re.Match) -> str:  # type: ignore[type-arg]
        return "{" + m.group(0)[1:-1].upper() + "}"

    return _SYMBOL_PATTERN.sub(_upper, text)
