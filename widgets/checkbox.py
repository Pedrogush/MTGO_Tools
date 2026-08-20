"""The app's checkbox — own-drawn, because wxMSW's cannot be made dark.

Why this control exists
-----------------------
``wx.CheckBox`` honours ``SetForegroundColour``/``SetBackgroundColour`` on its
*label* and ignores them on the box. The box is handed to ``wxRendererNative``,
which opens the standard light ``BUTTON`` visual style: a solid white square with
a dark tick, on every dark surface in the app, in all ten places one is used.

Everything cheaper than an own-drawn control was tried and measured first:

* seven theme classes against the native checkbox with Windows dark mode active
  (``DarkMode_Explorer``, ``DarkMode_CFD``, ``DarkMode``,
  ``DarkMode_Explorer::Button``, ``Explorer::Button``, ``DarkMode_ItemsView``,
  ``ItemsView``) — white in every one, checked and unchecked (phase 1);
* dropping the control out of visual styles — the classic path fills the box with
  ``COLOR_WINDOW``, which is also white (phase 1);
* ``wx.lib.checkbox.GenCheckBox``, wxPython's own generic checkbox — it is
  own-drawn *around* bitmaps it obtains from
  ``wx.RendererNative.Get().DrawCheckBox()``, i.e. from the exact light theme
  class that is the problem. Screenshotted side by side with ``wx.CheckBox``:
  pixel-identical white square (phase 2).

So the glyph has to be painted by us. That makes this a real control rather than
a styling call, which is why it landed with the phase-2 button system.

Compatibility
-------------
The ten call sites use ``GetValue``, ``SetValue``, ``IsChecked``, ``Enable``,
``SetToolTip`` and ``Bind(wx.EVT_CHECKBOX, ...)``; all of those behave exactly as
``wx.CheckBox``'s do, including ``SetValue`` **not** firing an event. The box is
drawn at ``wx.RendererNative``'s own checkbox metric, so replacing the native
control does not move a single pixel of surrounding layout.

Deliberately **not** supported: the three-state API (``wx.CHK_3STATE``,
``Set3StateValue``). No call site uses it, and a third state that only this
control can render would be a new visual idiom with no design token behind it.
Passing ``wx.CHK_3STATE`` raises rather than silently rendering two states.
"""

from __future__ import annotations

import wx

from utils.constants.theme import (
    ACCENT_ON_PRIMARY,
    ACCENT_PRIMARY,
    BORDER_STRONG,
    DISABLED_BORDER,
    DISABLED_FILL,
    DISABLED_ON_FILL,
    FOCUS_RING,
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    SURFACE_RAISED,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

_SURFACES = {
    "base": SURFACE_BASE,
    "panel": SURFACE_PANEL,
    "alt": SURFACE_ALT,
    "raised": SURFACE_RAISED,
}
_TONES = {
    "primary": TEXT_PRIMARY,
    "secondary": TEXT_SECONDARY,
    "disabled": TEXT_DISABLED,
}

#: Gap between the box and the label, in pixels. Matches what wxMSW leaves
#: between a native checkbox glyph and its label, so swapping the control in does
#: not change any row's width.
_LABEL_GAP = 4

#: Fallback box edge when ``wx.RendererNative`` cannot be asked (headless tests).
_FALLBACK_BOX = 13


def _c(rgb: tuple[int, int, int]) -> wx.Colour:
    return wx.Colour(*rgb)


class DarkCheckBox(wx.Control):
    """A two-state checkbox that is actually dark.

    Drop-in for ``wx.CheckBox`` at every call site in this app. Emits
    ``wx.EVT_CHECKBOX`` on user interaction (click or space), never on
    :meth:`SetValue`.
    """

    def __init__(
        self,
        parent: wx.Window,
        id: int = wx.ID_ANY,  # noqa: A002 - mirrors the wx.CheckBox signature
        label: str = "",
        pos: wx.Point = wx.DefaultPosition,
        size: wx.Size = wx.DefaultSize,
        style: int = 0,
        validator: wx.Validator = wx.DefaultValidator,
        name: str = "DarkCheckBox",
    ) -> None:
        if style & (wx.CHK_3STATE | wx.CHK_ALLOW_3RD_STATE_FOR_USER):
            raise ValueError(
                "DarkCheckBox is two-state only; no call site uses wx.CHK_3STATE and "
                "the design system has no token for an indeterminate box"
            )
        super().__init__(parent, id, pos, size, style | wx.BORDER_NONE, validator, name)

        self._checked = False
        self._hover = False
        self._surface = SURFACE_PANEL
        self.SetForegroundColour(_c(TEXT_PRIMARY))
        self.SetBackgroundColour(_c(SURFACE_PANEL))
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.SetLabel(label)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda _evt: None)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_left_down)
        self.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_SET_FOCUS, self._on_focus_change)
        self.Bind(wx.EVT_KILL_FOCUS, self._on_focus_change)

    # -- wx.CheckBox-compatible API ------------------------------------
    def GetValue(self) -> bool:  # noqa: N802 - wx API
        return self._checked

    def IsChecked(self) -> bool:  # noqa: N802 - wx API
        return self._checked

    def SetValue(self, state: bool) -> None:  # noqa: N802 - wx API
        """Set the state **without** firing ``EVT_CHECKBOX``, as wx.CheckBox does."""
        state = bool(state)
        if state == self._checked:
            return
        self._checked = state
        self.Refresh()

    def SetLabel(self, label: str) -> None:  # noqa: N802 - wx API
        super().SetLabel(label)
        self.InvalidateBestSize()
        self.Refresh()

    def SetFont(self, font: wx.Font) -> bool:  # noqa: N802 - wx API
        result = super().SetFont(font)
        self.InvalidateBestSize()
        self.Refresh()
        return result

    def Enable(self, enable: bool = True) -> bool:  # noqa: N802 - wx API
        result = super().Enable(enable)
        self.Refresh()
        return result

    def AcceptsFocus(self) -> bool:  # noqa: N802 - wx API
        return self.IsEnabled()

    def AcceptsFocusFromKeyboard(self) -> bool:  # noqa: N802 - wx API
        return self.IsEnabled()

    # -- theming --------------------------------------------------------
    def apply_theme(self, *, surface: str = "base", tone: str = "primary") -> None:
        """Put the control on ``surface`` with the ``tone`` label colour.

        Called by :func:`widgets.stylize.stylize_checkbox` so that call sites keep
        using one styling entry point for both this control and any remaining
        ``wx.CheckBox``.
        """
        self._surface = _SURFACES[surface]
        self.SetBackgroundColour(_c(self._surface))
        self.SetForegroundColour(_c(_TONES[tone]))
        self.Refresh()

    # -- geometry -------------------------------------------------------
    def _box_size(self) -> int:
        try:
            return int(wx.RendererNative.Get().GetCheckBoxSize(self).GetWidth())
        except Exception:  # pragma: no cover - headless / very old wx
            return _FALLBACK_BOX

    def DoGetBestSize(self) -> wx.Size:  # noqa: N802 - wx API
        dc = wx.ClientDC(self)
        dc.SetFont(self.GetFont())
        text_w, text_h = dc.GetTextExtent(self.GetLabel())
        box = self._box_size()
        best = wx.Size(box + _LABEL_GAP + text_w, max(box, text_h))
        self.CacheBestSize(best)
        return best

    # -- painting -------------------------------------------------------
    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        dc.SetBackground(wx.Brush(self.GetBackgroundColour()))
        dc.Clear()
        self._draw(dc)

    def _draw(self, dc: wx.DC) -> None:
        width, height = self.GetClientSize()
        if not width or not height:
            return
        enabled = self.IsEnabled()
        box = self._box_size()
        box_y = (height - box) // 2

        if not enabled:
            fill, border = DISABLED_FILL, DISABLED_BORDER
            tick = DISABLED_ON_FILL
        elif self._checked:
            # The one place the saturated accent appears at control scale: the
            # affirmative state. Unchecked stays neutral, so the colour marks the
            # state rather than the control.
            fill, border = ACCENT_PRIMARY, ACCENT_PRIMARY
            tick = ACCENT_ON_PRIMARY
        else:
            fill = SURFACE_ALT
            border = TEXT_SECONDARY if self._hover else BORDER_STRONG
            tick = ACCENT_ON_PRIMARY

        dc.SetBrush(wx.Brush(_c(fill)))
        dc.SetPen(wx.Pen(_c(border), 1))
        dc.DrawRectangle(0, box_y, box, box)

        if self._checked:
            dc.SetPen(wx.Pen(_c(tick), 2))
            # A tick, in box-relative units, scaled to whatever metric the
            # renderer reports so it stays centred at any DPI.
            left = (0.22 * box, box_y + 0.52 * box)
            mid = (0.42 * box, box_y + 0.72 * box)
            right = (0.78 * box, box_y + 0.28 * box)
            dc.DrawLines([wx.Point(int(x), int(y)) for x, y in (left, mid, right)])

        dc.SetFont(self.GetFont())
        dc.SetTextForeground(self.GetForegroundColour() if enabled else _c(TEXT_DISABLED))
        label = self.GetLabel()
        _, text_h = dc.GetTextExtent(label)
        dc.DrawText(label, box + _LABEL_GAP, (height - text_h) // 2)

        if self.HasFocus():
            # Outside the box, never inside it: FOCUS_RING is only 1.82:1 against
            # ACCENT_PRIMARY, so a ring drawn on a checked box would be invisible
            # (phase 0 finding). On the surrounding surface it is >= 6:1.
            dc.SetBrush(wx.TRANSPARENT_BRUSH)
            pen = wx.Pen(_c(FOCUS_RING), 1, wx.PENSTYLE_USER_DASH)
            pen.SetDashes([1, 1])
            dc.SetPen(pen)
            dc.DrawRectangle(0, 0, width, height)

    # -- interaction ----------------------------------------------------
    def _on_left_down(self, event: wx.MouseEvent) -> None:
        if not self.IsEnabled():
            return
        self.SetFocus()
        self._toggle()
        event.Skip()

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        if event.GetKeyCode() == wx.WXK_SPACE and self.IsEnabled():
            self._toggle()
            return
        event.Skip()

    def _on_enter(self, _event: wx.MouseEvent) -> None:
        self._hover = True
        self.Refresh()

    def _on_leave(self, _event: wx.MouseEvent) -> None:
        self._hover = False
        self.Refresh()

    def _on_focus_change(self, event: wx.FocusEvent) -> None:
        self.Refresh()
        event.Skip()

    def _toggle(self) -> None:
        self._checked = not self._checked
        self.Refresh()
        event = wx.CommandEvent(wx.wxEVT_CHECKBOX, self.GetId())
        event.SetInt(int(self._checked))
        event.SetEventObject(self)
        self.GetEventHandler().ProcessEvent(event)


__all__ = ["DarkCheckBox"]
