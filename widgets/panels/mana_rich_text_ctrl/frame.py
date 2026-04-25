"""UI construction for the mana-symbol-aware rich-text control.

Renders ``{W}``, ``{R/G}``, ``{2/W}`` etc. as inline images while keeping the
brace-notation string as the canonical value returned by ``GetValue()``.

Why this is a wx.Panel, not a wx.richtext.RichTextCtrl: the native
TextCtrl's blue focus underline is painted by Windows' uxtheme on the
EDIT control's non-client area, which a custom-drawn RichTextCtrl can't
receive. To match the look we paint the whole 2-DIP grey frame ourselves
-- replicating the outer/inner two-tone composition sampled from an
adjacent native wx.TextCtrl -- and tint the whole bottom band to the
Windows system accent colour on focus. The actual rich-text buffer is
a borderless child RichTextCtrl that fills the panel interior.

The placeholder hint is a separate ``wx.StaticText`` overlay rather than
text written into the rich-text buffer. Writing the hint into the buffer
(with a grey character style) leaves residue that contaminates later
typed characters -- the overlay approach keeps the buffer's style
pristine so typed text always renders in the single persistent dark
style set once in __init__.

Input modes (mutually exclusive, optional):
  mana_key_input    -- every key is captured; single letters and two-key
                       chords resolve to mana symbols (mana-cost box).
  ctrl_m_mana_mode  -- regular text entry until Ctrl+M toggles into the
                       mana_key_input flow (oracle-text search).

Without either flag the control is a read-through display whose Ctrl+C
copies the canonical plain-text value rather than the RTF placeholder.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
import wx.richtext

from utils.constants import DARK_ALT, HINT_TEXT, LIGHT_TEXT
from widgets.panels.mana_rich_text_ctrl.handlers import (
    ManaRichTextInnerHandlersMixin,
    ManaSymbolRichCtrlHandlersMixin,
)
from widgets.panels.mana_rich_text_ctrl.properties import (
    ManaRichTextInnerPropertiesMixin,
    ManaSymbolRichCtrlPropertiesMixin,
)

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


class _ManaRichTextInner(
    ManaRichTextInnerHandlersMixin,
    ManaRichTextInnerPropertiesMixin,
    wx.richtext.RichTextCtrl,
):
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


class ManaSymbolRichCtrl(
    ManaSymbolRichCtrlHandlersMixin,
    ManaSymbolRichCtrlPropertiesMixin,
    wx.Panel,
):
    """Public wrapper. Custom-paints a 2-DIP frame matching the native Win11
    dark-mode wx.TextCtrl outline (outer light halo + inner near-white
    ring, with a darker outer row at the bottom that tints the Windows
    system accent colour on focus); delegates the TextCtrl API to an
    inner borderless RichTextCtrl that fills the panel interior.
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
