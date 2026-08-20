"""UI construction for the mana-symbol-aware rich-text control.

Renders ``{W}``, ``{R/G}``, ``{2/W}`` etc. as inline images while keeping the
brace-notation string as the canonical value returned by ``GetValue()``.

Why this is a wx.Panel, not a wx.richtext.RichTextCtrl: the native
TextCtrl's focus underline is painted by Windows' uxtheme on the EDIT
control's non-client area, which a custom-drawn RichTextCtrl can't
receive. So the whole 2-DIP frame is painted here. The actual rich-text
buffer is a borderless child RichTextCtrl that fills the panel interior.

Phase 6b re-founded that frame on the design tokens. It was sampled from
an adjacent *native* wx.TextCtrl and reproduced literally -- ``#ECECEC``
outer over a ``#FEFEFE`` inner ring -- which is the same near-white
sunken client edge :func:`widgets.stylize.strip_native_client_edge` was
written to delete from every other input in the app. Measured on the
running builder: two 545x24 rectangles outlined at **15.6:1 against
SURFACE_PANEL**, on the main window, in the panel with the most use.
Copying the platform was the bug; the app is not drawn in the platform's
palette any more.

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
from utils.constants.theme import BORDER_SUBTLE, FOCUS_RING
from widgets.panels.mana_rich_text_ctrl.handlers import (
    ManaRichTextInnerHandlersMixin,
    ManaSymbolRichCtrlHandlersMixin,
)
from widgets.panels.mana_rich_text_ctrl.properties import (
    ManaRichTextInnerPropertiesMixin,
    ManaSymbolRichCtrlPropertiesMixin,
)
from widgets.stylize import theme_font

if TYPE_CHECKING:
    from widgets.mana_icon_factory import ManaIconFactory


# The frame keeps its three-tone composition and its 2-DIP geometry -- a
# 1-DIP halo wrapping a 1-DIP ring, darker along the bottom -- because the
# inner RichTextCtrl is laid out inside that inset and changing it reflows
# four call sites. What changed in phase 6b is where the three colours come
# from.
#
# BORDER_SUBTLE throughout, which is the same call phase 6 made for all ten
# section cards: a quiet edge. BORDER_STRONG was tried first, on the argument
# that the ring is the only thing identifying an input -- and measured against
# the real builder it was wrong, because a stripped ``wx.TextCtrl`` in this app
# renders with **no border at all**, so a 3.54:1 ring here would have made
# these two fields the loud ones in a column of five. Whether a text input on
# SURFACE_PANEL needs a visible boundary at all is a live question (its fill is
# 1.10:1 on panel), but it is one question with one answer for every field, not
# something this control gets to decide alone.
_BORDER_HALO = wx.Colour(*BORDER_SUBTLE)
_BORDER_RING = wx.Colour(*BORDER_SUBTLE)
_BORDER_BASE = wx.Colour(*BORDER_SUBTLE)
#: The focus underline. Was ``wx.SYS_COLOUR_HIGHLIGHT`` -- the *system*
#: accent, a user setting rather than a token of ours, which phase 2
#: rejected for exactly this reason when it looked at wx.ToggleButton's
#: checked ring. FOCUS_RING is 7.43:1 on SURFACE_ALT and is drawn outside
#: the field, which is where phase 0 said a focus ring has to live.
_BORDER_FOCUS = wx.Colour(*FOCUS_RING)
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

        # theme_font(), not wx.SYS_DEFAULT_GUI_FONT: this control is created
        # under a parent that already carries the app's 10pt base, and asking
        # the *system* for a font silently put it back to 9pt. Phase 3 wired
        # apply_base_font into all 18 top-level windows and this was the one
        # widget that re-fetched the platform default afterwards.
        font = theme_font()
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
        self.SetBackgroundColour(_BORDER_HALO)

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
