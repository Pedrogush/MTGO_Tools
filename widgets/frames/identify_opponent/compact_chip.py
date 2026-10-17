"""The compact tracker chip: a small floating, always-on-top window.

It shows the opponent archetype's initials with a status dot and a padlock.
Hovering it opens a card with the tracker's information; clicking it (not the
padlock) brings the full tracker back.

The padlock toggles dragging. Unlocked, the chip can be dragged anywhere;
locked, a press can't move it by accident in the middle of a game. The chip
never takes focus away from MTGO: it is a tool window that does not activate
(``WS_EX_NOACTIVATE`` on Windows), and the hover card is a ``wx.PopupWindow``,
which never activates either.
"""

from __future__ import annotations

import ctypes
import os
from collections.abc import Callable, Sequence

import wx

from utils.constants import (
    BORDER_STRONG,
    BORDER_SUBTLE,
    SPACE_SM,
    SPACE_XS,
    SUCCESS_TEXT,
    SURFACE_PANEL,
    SURFACE_RAISED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    WARNING_TEXT,
)
from widgets.frames.identify_opponent.compact import (
    ChipFace,
    ChipState,
    HoverSection,
    popup_position,
)
from widgets.section import SECTION_BORDER_WIDTH
from widgets.stylize import type_font

#: The chip's size (px): initials on the left, padlock on the right.
CHIP_SIZE = (76, 32)
#: The padlock's square hit area at the chip's right edge (px).
_LOCK_BOX = 20
#: A press that moves less than this is a click, not a drag (px).
_DRAG_THRESHOLD = 4
#: How often the open hover card checks whether the pointer has left (ms).
_HOVER_CHECK_MS = 150
#: Widest the hover card's text may run before it wraps (px).
_POPUP_WRAP_WIDTH = 320

_STATE_DOT_COLOURS = {
    ChipState.IDLE: TEXT_SECONDARY,
    ChipState.UNKNOWN: WARNING_TEXT,
    ChipState.KNOWN: SUCCESS_TEXT,
}

_GWL_EXSTYLE = -20
_WS_EX_NOACTIVATE = 0x08000000


def _make_non_activating(window: wx.Window) -> None:
    """Stop clicks on ``window`` from activating it (and deactivating MTGO)."""
    if os.name != "nt":
        return
    try:
        user32 = ctypes.WinDLL("user32")
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
        hwnd = window.GetHandle()
        style = user32.GetWindowLongPtrW(hwnd, _GWL_EXSTYLE)
        user32.SetWindowLongPtrW(hwnd, _GWL_EXSTYLE, style | _WS_EX_NOACTIVATE)
    except (OSError, AttributeError):
        pass  # the chip still works; a click just activates it


class _HoverCard(wx.PopupWindow):
    """The card the chip opens on hover: a headline, then one block per section."""

    def __init__(self, parent: wx.Window) -> None:
        super().__init__(parent, flags=wx.BORDER_NONE)
        # A 1px border panel with the body inset inside it, as in
        # widgets/section.py: background colours are honoured everywhere,
        # paint handlers are not.
        self.SetBackgroundColour(BORDER_STRONG)
        self._body = wx.Panel(self)
        self._body.SetBackgroundColour(SURFACE_RAISED)
        outer = wx.BoxSizer(wx.VERTICAL)
        outer.Add(self._body, 1, wx.EXPAND | wx.ALL, SECTION_BORDER_WIDTH)
        self.SetSizer(outer)
        self._sizer = wx.BoxSizer(wx.VERTICAL)
        self._body.SetSizer(self._sizer)

    def set_content(
        self, headline: str, sections: Sequence[HoverSection], footer: str = ""
    ) -> None:
        self._body.DestroyChildren()
        self._sizer.Clear()
        self._add_text(headline, level="heading", colour=TEXT_PRIMARY, top=SPACE_SM)
        for section in sections:
            self._add_text(section.heading, level="body", colour=TEXT_PRIMARY, top=SPACE_SM)
            self._add_text("\n".join(section.lines), level="caption", colour=TEXT_SECONDARY)
        if footer:
            self._add_text(footer, level="caption", colour=TEXT_SECONDARY, top=SPACE_SM)
        self._sizer.AddSpacer(SPACE_SM)
        # Size to the content as wrapped: fit the body first, then this
        # window around it (plus the 1px border on each side).
        self.fit_to_content()

    def fit_to_content(self) -> None:
        """Size the card to its text plus the 1px border on each side.

        Run again once the card is on screen: before that, wxGTK measures the
        wrapped labels taller than they end up, which left a band of empty card
        under the last line.
        """
        for child in self._body.GetChildren():
            child.InvalidateBestSize()
        content = self._sizer.GetMinSize()
        edge = 2 * SECTION_BORDER_WIDTH
        self.SetSize(wx.Size(content.width + edge, content.height + edge))
        self.Layout()

    def _add_text(self, text: str, *, level: str, colour: tuple, top: int = SPACE_XS) -> None:
        label = wx.StaticText(self._body, label=text)
        label.SetFont(type_font(level))
        label.SetForegroundColour(colour)
        label.SetBackgroundColour(SURFACE_RAISED)
        label.Wrap(_POPUP_WRAP_WIDTH)
        # Headings get the full gap above them; a section's lines sit close
        # under its heading.
        self._sizer.AddSpacer(top)
        self._sizer.Add(label, 0, wx.LEFT | wx.RIGHT, SPACE_SM)


class OpponentChip(wx.Frame):
    """Floating chip for the tracker's compact mode.

    :param on_expand: called when the chip is clicked (not dragged, not on the
        padlock): the owner brings the full tracker back.
    :param on_moved: called with the new top-left after a drag ends.
    :param on_lock_changed: called with the new locked state.
    :param hover_content: called when the hover card opens; returns the
        headline and the sections to show, so the card always shows the
        tracker's *current* state rather than a copy made when it changed.
    """

    def __init__(
        self,
        parent: wx.Window | None,
        *,
        on_expand: Callable[[], None],
        on_moved: Callable[[tuple[int, int]], None],
        on_lock_changed: Callable[[bool], None],
        hover_content: Callable[[], tuple[str, Sequence[HoverSection]]],
        locked_hint: str = "",
        unlocked_hint: str = "",
    ) -> None:
        super().__init__(
            parent,
            size=CHIP_SIZE,
            style=(wx.FRAME_NO_TASKBAR | wx.STAY_ON_TOP | wx.FRAME_TOOL_WINDOW | wx.BORDER_NONE),
        )
        self._on_expand = on_expand
        self._on_moved = on_moved
        self._on_lock_changed = on_lock_changed
        self._hover_content = hover_content
        # How to use the chip, as the hover card's last line. Not a tooltip:
        # a tooltip opens under the pointer, right on top of the card.
        self._locked_hint = locked_hint
        self._unlocked_hint = unlocked_hint

        self._face = ChipFace("–", ChipState.IDLE)
        self._locked = True
        self._press_screen: wx.Point | None = None
        self._press_origin: wx.Point | None = None
        self._dragging = False

        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)
        self.Bind(wx.EVT_ENTER_WINDOW, self._on_enter)

        self._card = _HoverCard(self)
        self._hover_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_hover_check, self._hover_timer)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

        _make_non_activating(self)

    # ---- public API -----------------------------------------------------

    def set_face(self, face: ChipFace) -> None:
        if face == self._face:
            return
        self._face = face
        self.Refresh()

    def set_locked(self, locked: bool) -> None:
        self._locked = locked
        self.Refresh()

    @property
    def locked(self) -> bool:
        return self._locked

    def show_at(self, position: tuple[int, int]) -> None:
        self.SetPosition(wx.Point(*position))
        if not self.IsShown():
            # Never steal focus from MTGO just by appearing.
            self.ShowWithoutActivating()

    def hide(self) -> None:
        self._close_card()
        self.Hide()

    # ---- painting -------------------------------------------------------

    def _lock_rect(self) -> wx.Rect:
        w, h = self.GetClientSize()
        return wx.Rect(w - _LOCK_BOX - SPACE_XS, (h - _LOCK_BOX) // 2, _LOCK_BOX, _LOCK_BOX)

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        w, h = self.GetClientSize()
        dc.SetBackground(wx.Brush(wx.Colour(*SURFACE_PANEL)))
        dc.Clear()
        gc = wx.GraphicsContext.Create(dc)
        if gc is None:
            return
        border = BORDER_SUBTLE if self._locked else BORDER_STRONG
        gc.SetPen(wx.Pen(wx.Colour(*border), 1))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        gc.DrawRectangle(0, 0, w - 1, h - 1)

        # Status dot, then the initials.
        dot = 8
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(wx.Colour(*_STATE_DOT_COLOURS[self._face.state])))
        gc.DrawEllipse(SPACE_SM, (h - dot) / 2, dot, dot)

        font = type_font("body", bold=True)
        gc.SetFont(font, wx.Colour(*TEXT_PRIMARY))
        tw, th = gc.GetTextExtent(self._face.label)[:2]
        text_left = SPACE_SM + dot + SPACE_XS
        text_right = self._lock_rect().GetLeft() - SPACE_XS
        tx = text_left + max(0, (text_right - text_left - tw) / 2)
        gc.DrawText(self._face.label, tx, (h - th) / 2)

        self._draw_padlock(gc, self._lock_rect())

    def _draw_padlock(self, gc: wx.GraphicsContext, box: wx.Rect) -> None:
        """A padlock: closed shackle while locked, swung open while unlocked."""
        colour = wx.Colour(*(TEXT_SECONDARY if self._locked else TEXT_PRIMARY))
        body_w, body_h = 12, 9
        bx = box.x + (box.width - body_w) / 2
        by = box.y + box.height - body_h - 2
        gc.SetPen(wx.Pen(colour, 2))
        gc.SetBrush(wx.TRANSPARENT_BRUSH)
        shackle = gc.CreatePath()
        radius = 3.5
        left = bx + 2.5
        right = bx + body_w - 2.5
        top = by - 7
        if self._locked:
            shackle.MoveToPoint(left, by)
            shackle.AddLineToPoint(left, top + radius)
            shackle.AddArc(left + radius, top + radius, radius, 3.14159, 0, True)
            shackle.AddLineToPoint(right, by)
        else:
            # Swung open: the left leg lifts clear of the body.
            shackle.MoveToPoint(left, by - 3)
            shackle.AddLineToPoint(left, top + radius - 2)
            shackle.AddArc(left + radius, top + radius - 2, radius, 3.14159, 0, True)
            shackle.AddLineToPoint(right, by)
        gc.StrokePath(shackle)
        gc.SetPen(wx.TRANSPARENT_PEN)
        gc.SetBrush(wx.Brush(colour))
        gc.DrawRoundedRectangle(bx, by, body_w, body_h, 2)

    # ---- mouse ----------------------------------------------------------

    def _on_left_down(self, event: wx.MouseEvent) -> None:
        if self._lock_rect().Contains(event.GetPosition()):
            self.set_locked(not self._locked)
            self._on_lock_changed(self._locked)
            return
        self._press_screen = wx.GetMousePosition()
        self._press_origin = self.GetPosition()
        self._dragging = False
        if not self.HasCapture():
            self.CaptureMouse()

    def _on_motion(self, event: wx.MouseEvent) -> None:
        if self._press_screen is None or not event.LeftIsDown() or self._locked:
            return
        now = wx.GetMousePosition()
        dx = now.x - self._press_screen.x
        dy = now.y - self._press_screen.y
        if not self._dragging and max(abs(dx), abs(dy)) < _DRAG_THRESHOLD:
            return
        if not self._dragging:
            self._dragging = True
            self._close_card()
        assert self._press_origin is not None
        self.SetPosition(wx.Point(self._press_origin.x + dx, self._press_origin.y + dy))

    def _on_left_up(self, _event: wx.MouseEvent) -> None:
        if self.HasCapture():
            self.ReleaseMouse()
        if self._press_screen is None:
            return
        dragged = self._dragging
        self._press_screen = None
        self._press_origin = None
        self._dragging = False
        if dragged:
            pos = self.GetPosition()
            self._on_moved((pos.x, pos.y))
        else:
            self._close_card()
            self._on_expand()

    def _on_capture_lost(self, _event: wx.MouseCaptureLostEvent) -> None:
        self._press_screen = None
        self._press_origin = None
        self._dragging = False

    # ---- hover card -----------------------------------------------------

    def _on_enter(self, _event: wx.MouseEvent) -> None:
        if self._dragging or self._card.IsShown():
            return
        headline, sections = self._hover_content()
        hint = self._locked_hint if self._locked else self._unlocked_hint
        self._card.set_content(headline, sections, hint)
        display_idx = wx.Display.GetFromWindow(self)
        area = wx.Display(display_idx if display_idx != wx.NOT_FOUND else 0).GetClientArea()
        rect = self.GetScreenRect()
        size = self._card.GetSize()
        x, y = popup_position(
            (rect.x, rect.y, rect.width, rect.height),
            (size.width, size.height),
            (area.x, area.y, area.width, area.height),
        )
        self._card.SetPosition(wx.Point(x, y))
        self._card.Show()
        wx.CallAfter(self._refit_card)
        self._hover_timer.Start(_HOVER_CHECK_MS)

    def _refit_card(self) -> None:
        if self._card.IsShown():
            self._card.fit_to_content()

    def _on_hover_check(self, _event: wx.TimerEvent) -> None:
        """Close the card once the pointer is over neither the chip nor the card.

        Polled rather than driven by EVT_LEAVE_WINDOW: moving from the chip onto
        the card is a leave too, and the card has to stay open for that.
        """
        pointer = wx.GetMousePosition()
        if self.GetScreenRect().Contains(pointer):
            return
        if self._card.IsShown() and self._card.GetScreenRect().Contains(pointer):
            return
        self._close_card()

    def _close_card(self) -> None:
        if self._hover_timer.IsRunning():
            self._hover_timer.Stop()
        if self._card.IsShown():
            self._card.Hide()

    def _on_destroy(self, event: wx.WindowDestroyEvent) -> None:
        if event.GetEventObject() is self and self._hover_timer.IsRunning():
            self._hover_timer.Stop()
        event.Skip()
