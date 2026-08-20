"""The app's spin control — own-drawn arrows, because wxMSW's cannot be made dark.

Why this control exists
=======================
A wxMSW ``wx.SpinCtrl`` is **two HWNDs**: an ``Edit`` and an
``msctls_updown32``. The colours wx forwards reach the ``Edit``; nothing reaches
the arrows. Measured off phase 9's captures, the arrow pair renders ``#ECECEC``
(**12.6:1** on ``SURFACE_PANEL``) in the opponent tracker and ``#F0F0F0``
(**13.2:1**) in the timer alert — six controls across two windows, and once the
``wx.Button`` frame, the ``wx.StaticBox`` groove, the splitter sash and the
notebook's tab line had gone, the brightest chrome left in the app. It was the
last open half of acceptance criterion 1 of issue #962: *no native-light widget
anywhere on a dark surface*.

Everything cheaper was tried and measured first, twice:

* phase 1 — ``DarkMode_CFD``, Windows' own process dark mode, and dropping the
  control out of visual styles entirely: light grey in all three;
* phase 9b — an eight-variant probe on the up-down HWND itself
  (``DarkMode_CFD``, ``DarkMode_Explorer``, ``DarkMode_Explorer::SPIN``,
  ``DarkMode::SPIN``, ``DarkMode_CFD::SPIN``, ``ItemsView``, no visual style,
  untouched), each with ``AllowDarkModeForWindow`` + ``WM_THEMECHANGED``:
  **pixel-identical light arrows in all eight**. The ``Edit`` half *does* pick
  up dark mode in the same probe, which is what makes the split so easy to miss.

``wx.SpinButton`` is not a way out — it is the same ``msctls_updown32`` class —
and neither is ``wx.lib.agw.floatspin``, which builds one. So the arrows have to
be painted by us, as the menu bar (phase 3b), the FlatNotebook renderer
(phase 6), the data grid (phase 5), the splitter sash (phase 6b), the checkbox
(phase 2) and the text-input border (phase 6c) already are.

What this is
============
:class:`DarkSpinCtrl` is an :class:`widgets.input_frame.InputFrame` — the same
own-drawn border every text field in the app now has — hosting a real
``wx.TextCtrl`` plus one own-drawn arrow window inside the ring. The field is
an ordinary native ``Edit``: caret, selection, IME, clipboard and key handling
are untouched, exactly as in phase 6c. Only the arrows and the value logic are
ours.

That also closes a gap phase 6c left: the six spin *fields* were never routed
through ``create_text_input``, so after phase 6b stripped their ``#FFFFFF``
client edge they were fill-only at 1.10:1, with nothing marking the control.
They now carry the same resting/focus ring as every other input.

The field is built **without** ``wx.BORDER_NONE``, and that is deliberate: on
wxMSW a ``wx.TextCtrl``'s best height carries its border reserve, so a
``BORDER_NONE`` field reports **17px** against a bordered one's **25px** --
measured side by side against a native ``wx.SpinCtrl``, which is 25. The
``#FFFFFF`` client edge is stripped the way every other field in the app strips
it, by ``stylize_textctrl`` at the Win32 level (``WS_EX_CLIENTEDGE``), which
does not touch the wx style bits the best size is computed from. So the control
is the same height as the native one it replaces and as every other input on
the surface, with no magic number anywhere.

Behaviour parity
================
The native control's behaviour was measured on the running app with real Win32
input before it was replaced (``keybd_event``/``mouse_event`` against the live
HWNDs, reading values back with ``WM_GETTEXT``), and this control reproduces it:

=========================  =================================================
native, measured           reproduced here
=========================  =================================================
click an arrow             ``+1`` / ``-1``
press and hold             ``+1`` at once, first repeat at ~550ms, then a
                           tick every ~120ms
hold acceleration          step 1, then 5 from ~2.3s, then 20 from ~5s — the
                           comctl32 default ``UDACCEL`` table
Up / Down keys             ``+1`` / ``-1``
PageUp / PageDown          **nothing** (comctl32 does not bind them, so
                           neither do we)
mouse wheel over the field ``+1`` / ``-1`` per notch
typing                     digits only; letters are rejected at the keystroke
out-of-range typed value   shown as typed, clamped when focus leaves
                           (``999`` -> ``250``, ``0`` -> ``1``)
an emptied field           clamps to ``min`` when focus leaves
tab order                  the field is a tab stop, the arrows are not
=========================  =================================================

Two deliberate differences, both improvements, both measured:

* **``wx.EVT_TEXT_ENTER`` now fires.** ``calculator_panel.py`` has bound it on
  all four tracker spins since before this redesign, and it has never fired:
  wxMSW only forwards ``EN_*`` to a ``wx.SpinCtrl``'s buddy when the control
  carries ``wx.TE_PROCESS_ENTER``, and none of the six sites passed it. Verified
  live against the native control: pressing Enter in the Deck Size field left
  the result label empty, while clicking ``Calculate`` filled it. This control
  builds its field with ``wx.TE_PROCESS_ENTER``, so Enter now calculates.
* **The field has a border again** (above).

Compatibility
=============
The six call sites use ``GetValue``, ``SetValue``, ``SetToolTip`` and
``Bind(wx.EVT_TEXT_ENTER, ...)``. ``GetMin``/``GetMax``/``SetRange`` are here
too because ``wx.SpinCtrl`` has them and a partial stand-in is worse than none.
As on ``wx.SpinCtrl``, :meth:`SetValue` is programmatic and fires **no** event;
every user-driven change fires ``wx.EVT_SPINCTRL`` **and** ``wx.EVT_TEXT``,
which propagate as command events so a call site can bind either on the control
itself.

Deliberately **not** supported: ``wx.SP_WRAP`` (no call site wraps, and a
wrapping deck size is a bug not a feature) and ``wx.SpinCtrlDouble``'s float
API. Both raise rather than silently rendering something else.
"""

from __future__ import annotations

import time

import wx

from utils.constants.theme import (
    BORDER_SUBTLE,
    SELECTION_FILL_ON_ALT,
    SURFACE_RAISED,
    TEXT_DISABLED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from widgets.input_frame import INPUT_BORDER_DIP, InputFrame
from widgets.stylize import stylize_textctrl, surface_colour

#: Width of the arrow column, in DIP. The native ``msctls_updown32`` measured
#: 17px at 100% DPI on both windows, and matching it keeps every row's geometry
#: where phases 3, 6 and 8 pinned it.
ARROW_WIDTH_DIP = 17

#: Delay before the first auto-repeat, and the interval between repeats after
#: it. Both measured off comctl32 by polling the live field through
#: ``WM_GETTEXT`` during a 6s hold: first repeat at 576ms, then a tick every
#: 79-200ms with a mean of ~120ms.
REPEAT_DELAY_MS = 500
REPEAT_INTERVAL_MS = 120

#: comctl32's default ``UDACCEL`` table: seconds held -> increment per tick.
#: Longest hold first, so the first match wins. Confirmed on the same trace —
#: the step went 1 -> 5 at t=2.33s.
REPEAT_ACCEL: tuple[tuple[float, int], ...] = ((5.0, 20), (2.0, 5), (0.0, 1))


def repeat_step(held_seconds: float) -> int:
    """The increment one auto-repeat tick applies after ``held_seconds``.

    Split out from the timer so the acceleration table can be asserted without a
    running window — holding a button is the behaviour most likely to be lost
    silently in a rewrite like this one, and it is the one a screenshot cannot
    show.
    """
    for threshold, step in REPEAT_ACCEL:
        if held_seconds >= threshold:
            return step
    return 1


def _c(rgb: tuple[int, int, int]) -> wx.Colour:
    return wx.Colour(*rgb)


class _SpinArrows(wx.Window):
    """The two arrow buttons. Own-drawn, never a tab stop, never focusable.

    Kept a plain ``wx.Window`` rather than two ``wx.Button``\\ s: a button pair
    would be two more HWNDs in the tab chain (the native arrows are not tab
    stops, and phase 6c showed how easily a wrapper adds one), would carry
    wxMSW's 75x25 best-size floor, and would need a timer each anyway for the
    auto-repeat that ``wx.EVT_BUTTON`` does not provide.
    """

    def __init__(self, parent: DarkSpinCtrl) -> None:
        super().__init__(parent, style=wx.BORDER_NONE)
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)
        self._owner = parent
        self._hover = 0  # +1 up, -1 down, 0 neither
        self._pressed = 0
        self._pressed_at = 0.0
        self._timer = wx.Timer(self)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_ERASE_BACKGROUND, lambda _evt: None)
        self.Bind(wx.EVT_LEFT_DOWN, self._on_left_down)
        self.Bind(wx.EVT_LEFT_DCLICK, self._on_left_down)
        self.Bind(wx.EVT_LEFT_UP, self._on_left_up)
        self.Bind(wx.EVT_MOTION, self._on_motion)
        self.Bind(wx.EVT_LEAVE_WINDOW, self._on_leave)
        self.Bind(wx.EVT_MOUSE_CAPTURE_LOST, self._on_capture_lost)
        self.Bind(wx.EVT_MOUSEWHEEL, self._on_wheel)
        self.Bind(wx.EVT_TIMER, self._on_timer)
        self.Bind(wx.EVT_WINDOW_DESTROY, self._on_destroy)

    # -- focus ----------------------------------------------------------
    def AcceptsFocus(self) -> bool:  # noqa: N802 - wx API
        """Never. The native arrows are not a tab stop and clicking them keeps
        the caret in the field, which is what makes click-then-type work."""
        return False

    def AcceptsFocusFromKeyboard(self) -> bool:  # noqa: N802 - wx API
        return False

    # -- geometry -------------------------------------------------------
    def _half(self, y: int) -> int:
        return 1 if y < self.GetClientSize().height // 2 else -1

    def _hit(self, event: wx.MouseEvent) -> int:
        size = self.GetClientSize()
        pos = event.GetPosition()
        if not (0 <= pos.x < size.width and 0 <= pos.y < size.height):
            return 0
        return self._half(pos.y)

    # -- painting -------------------------------------------------------
    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        width, height = self.GetClientSize()
        if not width or not height:
            return
        enabled = self._owner.IsInputEnabled() and self.IsEnabled()
        base = self._owner.field_fill()
        mid = height // 2

        dc.SetBackground(wx.Brush(base))
        dc.Clear()
        for direction, top, bottom in ((1, 0, mid), (-1, mid, height)):
            if enabled and self._pressed == direction:
                dc.SetBrush(wx.Brush(_c(SELECTION_FILL_ON_ALT)))
            elif enabled and self._hover == direction:
                dc.SetBrush(wx.Brush(_c(SURFACE_RAISED)))
            else:
                dc.SetBrush(wx.Brush(base))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(0, top, width, bottom - top)
            self._draw_arrow(dc, direction, top, bottom, width, enabled)

        # The two hairlines that make the arrows read as part of the field
        # rather than as a floating pair: one down the left edge, one between
        # the halves. BORDER_SUBTLE is decorative by phase 0's rule, which is
        # exactly what these are -- the control's sole marker is the frame's
        # own BORDER_STRONG ring.
        dc.SetPen(wx.Pen(_c(BORDER_SUBTLE), 1))
        dc.DrawLine(0, 0, 0, height)
        dc.DrawLine(0, mid, width, mid)

    def _draw_arrow(
        self, dc: wx.DC, direction: int, top: int, bottom: int, width: int, enabled: bool
    ) -> None:
        if not enabled:
            ink = TEXT_DISABLED
        elif self._hover == direction or self._pressed == direction:
            ink = TEXT_PRIMARY
        else:
            ink = TEXT_SECONDARY
        # 7x4 at 100% DPI, which is the native glyph's extent. Wider than it is
        # tall: a triangle drawn on a square makes a 17px column look crowded.
        half_w = max(2, self.FromDIP(3))
        half_h = max(1, self.FromDIP(2))
        cx = width // 2
        cy = (top + bottom) // 2
        tip = cy - half_h if direction > 0 else cy + half_h
        base_y = cy + half_h if direction > 0 else cy - half_h
        dc.SetBrush(wx.Brush(_c(ink)))
        dc.SetPen(wx.Pen(_c(ink), 1))
        dc.DrawPolygon(
            [
                wx.Point(cx, tip),
                wx.Point(cx - half_w, base_y),
                wx.Point(cx + half_w, base_y),
            ]
        )

    # -- interaction ----------------------------------------------------
    def _on_left_down(self, event: wx.MouseEvent) -> None:
        if not (self._owner.IsInputEnabled() and self.IsEnabled()):
            return
        direction = self._hit(event)
        if not direction:
            return
        self._pressed = direction
        self._pressed_at = time.monotonic()
        if not self.HasCapture():
            self.CaptureMouse()
        self.Refresh()
        self._owner.step(direction)
        self._timer.StartOnce(REPEAT_DELAY_MS)

    def _on_left_up(self, _event: wx.MouseEvent) -> None:
        self._stop()

    def _on_capture_lost(self, _event: wx.MouseCaptureLostEvent) -> None:
        # Do not touch the capture here: wx has already taken it away, and
        # calling ReleaseMouse() in this handler asserts.
        self._pressed = 0
        self._timer.Stop()
        self.Refresh()

    def _on_destroy(self, event: wx.WindowDestroyEvent) -> None:
        event.Skip()
        self._timer.Stop()

    def _stop(self) -> None:
        self._pressed = 0
        self._timer.Stop()
        if self.HasCapture():
            self.ReleaseMouse()
        self.Refresh()

    def _on_motion(self, event: wx.MouseEvent) -> None:
        event.Skip()
        hover = self._hit(event)
        if hover != self._hover:
            self._hover = hover
            self.Refresh()

    def _on_leave(self, _event: wx.MouseEvent) -> None:
        if self._hover:
            self._hover = 0
            self.Refresh()

    def _on_wheel(self, event: wx.MouseEvent) -> None:
        self._owner.wheel(event)

    def _on_timer(self, _event: wx.TimerEvent) -> None:
        if not self._pressed:
            return
        # Native behaviour: the repeat pauses while the pointer is off the
        # pressed arrow and resumes when it comes back, so the timer keeps
        # running either way.
        if self._pointer_on_pressed():
            self._owner.step(self._pressed, repeat_step(time.monotonic() - self._pressed_at))
        if not self._timer.IsRunning():
            # First tick: the one-shot delay timer has just expired, so turn it
            # into the periodic repeat. Chaining StartOnce instead was measured
            # and is wrong -- the handler's own cost is added to every interval,
            # which took the effective cadence from 120ms to ~200ms and left the
            # control a third slower than the native one over a 4s hold.
            self._timer.Start(REPEAT_INTERVAL_MS)

    def _pointer_on_pressed(self) -> bool:
        pos = self.ScreenToClient(wx.GetMousePosition())
        size = self.GetClientSize()
        if not (0 <= pos.x < size.width and 0 <= pos.y < size.height):
            return False
        return self._half(pos.y) == self._pressed


class DarkSpinCtrl(InputFrame):
    """A ``wx.SpinCtrl`` stand-in whose arrows are actually dark.

    Drop-in for the six sites in this app. See the module docstring for the
    measured behaviour table and for the two deliberate differences.
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        min: int = 0,  # noqa: A002 - mirrors the wx.SpinCtrl signature
        max: int = 100,  # noqa: A002 - mirrors the wx.SpinCtrl signature
        initial: int = 0,
        size: wx.Size | tuple[int, int] | None = None,
        surface: str = "alt",
        style: int = 0,
        name: str = "DarkSpinCtrl",
    ) -> None:
        if style & wx.SP_WRAP:
            raise ValueError(
                "DarkSpinCtrl does not wrap; no call site does, and a deck size "
                "that rolls over from 250 to 1 is a defect rather than a feature"
            )
        if min > max:
            raise ValueError(f"min {min} is above max {max}")
        # Set before super().__init__(): InputFrame lays out in its constructor
        # and this control's layout has to know the arrows are coming.
        self._arrows: _SpinArrows | None = None
        self._min = int(min)
        self._max = int(max)
        self._value = self._clamp(int(initial))
        self._updating = False

        super().__init__(
            parent,
            surface=surface,
            value=str(self._value),
            style=wx.TE_PROCESS_ENTER,
        )
        self.SetName(name)
        stylize_textctrl(self.ctrl, surface=surface)
        self.SetBackgroundColour(surface_colour(surface))

        self._arrows = _SpinArrows(self)
        self.ctrl.Bind(wx.EVT_KEY_DOWN, self._on_key_down)
        self.ctrl.Bind(wx.EVT_CHAR, self._on_char)
        self.ctrl.Bind(wx.EVT_TEXT, self._on_text)
        self.ctrl.Bind(wx.EVT_TEXT_ENTER, self._on_enter)
        self.ctrl.Bind(wx.EVT_KILL_FOCUS, self._on_commit_focus)
        self.ctrl.Bind(wx.EVT_MOUSEWHEEL, self.wheel)
        self.Bind(wx.EVT_MOUSEWHEEL, self.wheel)
        if size is not None:
            self.SetInitialSize(wx.Size(*size))
        self._layout_ctrl()

    # -- wx.SpinCtrl-compatible API --------------------------------------
    def GetValue(self) -> int:  # noqa: N802 - wx API
        return self._value

    def SetValue(self, value: int | str) -> None:  # noqa: N802 - wx API
        """Set the value programmatically. Fires no event, as ``wx.SpinCtrl``'s does not."""
        try:
            parsed = int(str(value).strip() or self._min)
        except ValueError:
            parsed = self._min
        self._value = self._clamp(parsed)
        self._write_text(self._value)

    def GetMin(self) -> int:  # noqa: N802 - wx API
        return self._min

    def GetMax(self) -> int:  # noqa: N802 - wx API
        return self._max

    def SetRange(self, min_value: int, max_value: int) -> None:  # noqa: N802 - wx API
        self._min, self._max = int(min_value), int(max_value)
        self.SetValue(self._value)

    def SetToolTip(self, tip: str | wx.ToolTip) -> None:  # noqa: N802 - wx API
        """Also put the tip on the field and the arrows.

        A tooltip set on a composite's outer window does not reach its children
        on wxMSW, and every pixel of this control *is* a child -- so without
        this the four tracker tooltips ("Total cards in deck (N)" and friends)
        would silently stop appearing. Each window gets its own ``wx.ToolTip``:
        wx takes ownership of the object it is handed.
        """
        text = tip if isinstance(tip, str) else tip.GetTip()
        super().SetToolTip(wx.ToolTip(text))
        for child in (self.ctrl, self._arrows):
            if child is not None:
                wx.Window.SetToolTip(child, wx.ToolTip(text))

    def EnableInput(self, enabled: bool = True) -> None:  # noqa: N802 - wx-style API
        super().EnableInput(enabled)
        if self._arrows is not None:
            self._arrows.Refresh()

    # -- value -----------------------------------------------------------
    def _clamp(self, value: int) -> int:
        return max(self._min, min(self._max, value))

    def field_fill(self) -> wx.Colour:
        """The colour the arrows paint behind themselves — the field's own fill."""
        return self.ctrl.GetBackgroundColour()

    def _write_text(self, value: int) -> None:
        text = str(value)
        if self.ctrl.GetValue() == text:
            return
        self._updating = True
        try:
            self.ctrl.ChangeValue(text)
            self.ctrl.SetInsertionPointEnd()
        finally:
            self._updating = False

    def _parse_field(self) -> int:
        """What is in the field right now, or the committed value if it is not a number."""
        text = self.ctrl.GetValue().strip()
        try:
            return int(text) if text and text != "-" else self._min
        except ValueError:
            return self._value

    def step(self, direction: int, amount: int = 1) -> None:
        """Move the value by ``direction * amount``, clamped, and notify.

        Steps from what is **in the field**, not from the last committed value:
        an out-of-range figure is allowed to stand while it is being typed (see
        :meth:`_on_text`), and clicking an arrow at that point should normalise
        it the way leaving the field would, not jump back to whatever was last
        in range.
        """
        if not self.IsInputEnabled():
            return
        target = self._clamp(self._clamp(self._parse_field()) + direction * amount)
        if target == self._value:
            return
        self._value = target
        self._write_text(target)
        self._notify()

    def wheel(self, event: wx.MouseEvent) -> None:
        """One notch, one step — what the native control does over its field."""
        rotation = event.GetWheelRotation()
        if rotation:
            self.step(1 if rotation > 0 else -1)

    def _notify(self) -> None:
        """Fire ``EVT_SPINCTRL`` and ``EVT_TEXT``, as ``wx.SpinCtrl`` does.

        Both are command events, so both propagate up from here and a call site
        can bind them on this control or on any ancestor.
        """
        spin = wx.SpinEvent(wx.wxEVT_SPINCTRL, self.GetId())
        spin.SetPosition(self._value)
        spin.SetInt(self._value)
        text = wx.CommandEvent(wx.wxEVT_TEXT, self.GetId())
        text.SetInt(self._value)
        text.SetString(str(self._value))
        for event in (spin, text):
            event.SetEventObject(self)
            self.GetEventHandler().ProcessEvent(event)

    # -- keyboard and typing ----------------------------------------------
    #: Up and down, cursor block **and** numeric keypad. The numpad pair is not
    #: cosmetic: with NumLock off the keypad's 8 and 2 send ``VK_UP``/``VK_DOWN``
    #: without ``KEYEVENTF_EXTENDEDKEY`` and wx reports them as
    #: ``WXK_NUMPAD_*``. The native control steps on those too -- measured,
    #: because a ``keybd_event`` harness sends exactly that form by default and
    #: comctl32 answered it.
    _STEP_KEYS = {wx.WXK_UP: 1, wx.WXK_NUMPAD_UP: 1, wx.WXK_DOWN: -1, wx.WXK_NUMPAD_DOWN: -1}

    def _on_key_down(self, event: wx.KeyEvent) -> None:
        direction = self._STEP_KEYS.get(event.GetKeyCode())
        if direction is None:
            event.Skip()
            return
        self.step(direction)

    def _on_char(self, event: wx.KeyEvent) -> None:
        """Digits only, the way the native ``Edit``'s ``ES_NUMBER`` filters them."""
        key = event.GetKeyCode()
        if key < wx.WXK_SPACE or key == wx.WXK_DELETE or key > 255:
            event.Skip()  # backspace, tab, enter, and every WXK_* navigation key
            return
        if event.ControlDown() or event.AltDown():
            event.Skip()
            return
        char = chr(key)
        if char.isdigit() or (char == "-" and self._min < 0):
            event.Skip()
        # else: swallowed, so the keystroke never reaches the field

    def _on_text(self, event: wx.CommandEvent) -> None:
        event.Skip()
        if self._updating:
            return
        text = self.ctrl.GetValue().strip()
        if not text or text == "-":
            return  # mid-edit; committed on Enter or focus loss
        try:
            typed = int(text)
        except ValueError:
            return
        # Deliberately *not* clamped here: the native control lets 999 stand in
        # a 1..250 field while you are still typing and clamps when focus
        # leaves. Clamping per keystroke makes "25" unreachable in a 1..20 field.
        if self._min <= typed <= self._max and typed != self._value:
            self._value = typed
            self._notify()

    def _on_enter(self, event: wx.CommandEvent) -> None:
        event.Skip()  # so a call site's EVT_TEXT_ENTER handler still runs
        self._commit()

    def _on_commit_focus(self, event: wx.FocusEvent) -> None:
        event.Skip()  # InputFrame repaints the ring off this event
        self._commit()

    def _commit(self) -> None:
        """Clamp what is in the field into range and rewrite it."""
        clamped = self._clamp(self._parse_field())
        changed = clamped != self._value
        self._value = clamped
        self._write_text(clamped)
        if changed:
            self._notify()

    # -- geometry ---------------------------------------------------------
    def _arrow_width(self) -> int:
        return self.FromDIP(ARROW_WIDTH_DIP)

    def DoGetBestSize(self) -> wx.Size:  # noqa: N802 - wx override
        """Widest value string + the arrow column, **not** the field's best size.

        ``InputFrame`` hands back ``wx.TextCtrl.GetBestSize()``, and phase 8
        measured that at a hard **110px** floor on wxMSW whatever the content —
        which is how the research Result row came to pin a 564px column for a
        two-digit number. Inheriting it here would widen the timer alert's
        options grid by ~60px per spin in a window that already wants more
        width than it has (phase 6). The digits are what this control holds, so
        the digits are what it is sized by.
        """
        dc = wx.ClientDC(self.ctrl)
        dc.SetFont(self.ctrl.GetFont())
        widest = max(str(self._min), str(self._max), key=len)
        text_w = dc.GetTextExtent(widest + "0").width
        inset = self.FromDIP(INPUT_BORDER_DIP)
        best = wx.Size(
            text_w + self._arrow_width() + 4 * inset,
            self.ctrl.GetBestSize().height,
        )
        self.CacheBestSize(best)
        return best

    def _layout_ctrl(self) -> None:
        size = self.GetClientSize()
        if size.width <= 0 or size.height <= 0:
            return
        inset = self.FromDIP(INPUT_BORDER_DIP)
        arrows = self._arrow_width() if self._arrows is not None else 0
        inner_h = max(0, size.height - 2 * inset)
        self.ctrl.SetSize(inset, inset, max(0, size.width - 2 * inset - arrows), inner_h)
        if self._arrows is not None:
            self._arrows.SetSize(max(inset, size.width - inset - arrows), inset, arrows, inner_h)


__all__ = ["ARROW_WIDTH_DIP", "DarkSpinCtrl", "repeat_step"]
