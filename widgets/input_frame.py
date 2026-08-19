"""The own-drawn border that marks a text input (issue #962, phase 6c).

Why this exists
===============
Phase 6b stripped the ``#FFFFFF`` sunken client edge wxMSW gives every
``wx.TextCtrl`` -- measured at ~21:1 against the dark surfaces around it, the
same near-white hairline the ``wx.StaticBox`` groove and the ``wx.Button``
frame had been. Removing it was right and left a different problem behind:
a field then renders as bare ``SURFACE_ALT`` on its parent, **1.10:1 on
``SURFACE_PANEL``**. Fill-only, with nothing marking where the field is.

Phase 0's rule (``utils/constants/theme.py``) is that ``BORDER_SUBTLE`` is
decorative and may sit below 3:1, while a border that is the **sole marker** of
a control must be ``BORDER_STRONG`` -- WCAG 1.4.11. A fill-only text field is
exactly the sole-marker case, and **wx cannot colour a ``wx.TextCtrl``'s border
at all**: the edge is non-client area painted by Windows, unreachable from
``SetBackgroundColour``, ``SetWindowTheme`` or any ``wx.BORDER_*`` flag other
than ``wx.BORDER_NONE``, which only deletes it. So the border has to be
own-drawn, as the menu bar (phase 3b), the FlatNotebook tab renderer (phase 6),
the data grid (phase 5), the splitter sash (phase 6b) and the checkbox
(phase 2) already are.

What this is, and what it deliberately is not
=============================================
:class:`InputFrame` is a **host**, not a wrapper. The ``wx.TextCtrl`` inside it
is an ordinary native control, constructed with the frame as its parent and
never reparented, subclassed or proxied. Call sites keep their reference to the
control itself and go on calling ``GetValue`` / ``ChangeValue`` / ``SetHint`` /
``Bind`` / ``SetFocus`` on it exactly as before; only the object handed to the
sizer changes. Nothing in this module sits between the user and the EDIT
control, which is why caret, selection, IME and key handling are untouched --
the brief's hard constraint. A delegating wrapper was rejected for the opposite
reason: ``Bind`` and ``SetFocus`` exist on ``wx.Panel``, so ``__getattr__``
delegation silently binds the wrong window rather than failing.

The architecture is not new here. ``ManaSymbolRichCtrl`` has shipped it since
before phase 6b -- a ``wx.Panel`` painting a 2-DIP frame around a borderless
inner control -- and phase 6c folds that control onto this module's painter so
there is one input border in the app rather than two.

Geometry and states
===================
The frame insets its child by ``INPUT_BORDER_DIP`` (2) on every side and paints
that band itself. The inset is constant across states, so **a focus change
never triggers a re-layout**; only the colour and the weight of the painted
ring change.

===========  ==================================  ==================
state        ring                                measured
===========  ==================================  ==================
resting      1 DIP ``BORDER_STRONG``             3.15 / 3.54 / 3.88 / 4.68:1
focused      2 DIP ``FOCUS_RING``                6.02 / 6.77 / 7.43 / 8.95:1
read-only    1 DIP ``BORDER_SUBTLE``             decorative, below 3:1 by design
disabled     1 DIP ``DISABLED_BORDER``           decorative
===========  ==================================  ==================

``FOCUS_RING`` is **1.82:1 against ``ACCENT_PRIMARY``**, so phase 0 forbids
drawing it inside a filled control. It is not filled here: the ring is painted
on the frame, *outside* the field's own fill, which is the placement phase 0
prescribed. The focused state changes both hue and weight, so it is
distinguishable from resting even to a reader who cannot separate the two
hues -- and a field that looked identical focused and unfocused would have been
a regression on the native edge this replaces.

``BORDER_SUBTLE`` for read-only, rather than ``BORDER_STRONG``, because WCAG
1.4.11 is about boundaries required to identify a control you can *act* on. A
read-only field is not an input target; it still gets the full focus ring when
focused, so 2.4.7 is unaffected.

What wxMSW does to a **disabled** ``wx.TextCtrl``
=================================================
Newly measured in phase 6c and now in ``widgets/stylize.py``'s table: a
disabled ``wx.TextCtrl`` **ignores ``SetBackgroundColour`` entirely** and paints
its client area ``#F0F0F0``. Setting the colour after ``Disable()``,
``disable_native_theme`` and Windows' own dark mode were all measured and all
leave the same near-white block -- so the one field in the app that is ever
disabled (the timer alert's threshold input) turns into a light rectangle the
moment the timer starts, and no border can rescue that.

:meth:`InputFrame.EnableInput` therefore renders "disabled" without asking wx to
disable the control: ``SetEditable(False)`` (which *does* keep the dark fill),
``DISABLED_FILL`` + ``DISABLED_TEXT``, and the frame stops accepting keyboard
focus so the field drops out of tab order the way a disabled control does. The
control stays technically enabled, so text in it remains selectable with the
mouse; that is the whole of the difference, and it is a better trade than a
white block.

Tab traversal
=============
Two things had to be got right and both were measured against a bare-control
baseline (identical orders):

* the frame is a ``wx.Panel`` **with ``wx.TAB_TRAVERSAL``**. ``wx.Panel``'s
  default style is ``wxTAB_TRAVERSAL``, and passing ``style=wx.BORDER_NONE``
  *replaces* it rather than adding to it -- which silently makes the frame a
  traversal dead end;
* ``AcceptsFocusFromKeyboard`` is delegated to the child. wxPanel's own
  implementation answers "do I have any focusable children" from
  ``AcceptsFocus``, which is ``True`` for a read-only or disabled
  ``wx.TextCtrl`` even though ``CanAcceptFocusFromKeyboard`` is ``False`` for
  both. Left alone, Tab lands on the **frame** -- a bare panel holding focus
  with no visible indicator. Delegating restores exactly the native order, in
  which wxMSW skips read-only and disabled fields.
"""

from __future__ import annotations

import wx

from utils.constants.theme import (
    BORDER_STRONG,
    BORDER_SUBTLE,
    DISABLED_BORDER,
    DISABLED_FILL,
    FOCUS_RING,
    TEXT_DISABLED,
)
from widgets.stylize import stylize_textctrl, surface_colour

#: Inset between the frame's edge and the field, on every side. Constant across
#: states so focus never reflows anything. Matches ``ManaSymbolRichCtrl``'s
#: existing 2-DIP frame, which this module now paints.
INPUT_BORDER_DIP = 2

#: Weight of the resting / read-only / disabled ring inside that band. The
#: focused ring uses the full ``INPUT_BORDER_DIP``.
INPUT_BORDER_RESTING_DIP = 1


def input_border_state(
    *, enabled: bool, focused: bool, editable: bool
) -> tuple[tuple[int, int, int], int]:
    """The ring colour and weight (in DIP) for one input state.

    Split out from the painter so the tokens can be asserted in a unit test
    without a running window -- the contrast suite is the regression guard for
    the whole redesign and this is the one border in the app that WCAG 1.4.11
    actually binds.
    """
    if not enabled:
        return DISABLED_BORDER, INPUT_BORDER_RESTING_DIP
    if focused:
        return FOCUS_RING, INPUT_BORDER_DIP
    if not editable:
        return BORDER_SUBTLE, INPUT_BORDER_RESTING_DIP
    return BORDER_STRONG, INPUT_BORDER_RESTING_DIP


def paint_input_border(
    window: wx.Window,
    dc: wx.DC,
    *,
    enabled: bool,
    focused: bool,
    editable: bool,
    fill: wx.Colour,
) -> None:
    """Paint the ring for ``window``'s current state, then its interior.

    Shared by :class:`InputFrame` and ``ManaSymbolRichCtrl`` so the app has one
    input border rather than two that drift apart. ``window`` is only used for
    ``GetClientSize`` and ``FromDIP``; the caller owns the DC.
    """
    size = window.GetClientSize()
    if size.width <= 0 or size.height <= 0:
        return
    colour, weight_dip = input_border_state(enabled=enabled, focused=focused, editable=editable)
    weight = max(1, window.FromDIP(weight_dip))
    dc.SetPen(wx.TRANSPARENT_PEN)
    dc.SetBrush(wx.Brush(wx.Colour(*colour)))
    dc.DrawRectangle(0, 0, size.width, size.height)
    dc.SetBrush(wx.Brush(fill))
    dc.DrawRectangle(
        weight,
        weight,
        max(0, size.width - 2 * weight),
        max(0, size.height - 2 * weight),
    )


class InputFrame(wx.Panel):
    """A painted border hosting exactly one native text control.

    Build one with :func:`create_text_input` rather than directly: the factory
    is the single ``wx.TextCtrl`` construction site in ``widgets/``, which is
    what lets ``tests/test_widget_audit.py`` fail on a new bare field.
    """

    def __init__(self, parent: wx.Window, *, surface: str = "alt", **ctrl_kwargs) -> None:
        # wx.TAB_TRAVERSAL is load-bearing; see the module docstring.
        super().__init__(parent, style=wx.TAB_TRAVERSAL | wx.BORDER_NONE)
        # Required by wx.AutoBufferedPaintDC: the ring and the interior are
        # both painted here, so the default erase pass has to be suppressed
        # (widgets/stylize.py, "Own-drawn surfaces").
        self.SetBackgroundStyle(wx.BG_STYLE_PAINT)

        self._surface = surface
        self._input_enabled = True
        self._last_enabled = True
        self.ctrl = wx.TextCtrl(self, **ctrl_kwargs)

        self.Bind(wx.EVT_PAINT, self._on_paint)
        self.Bind(wx.EVT_SIZE, self._on_size)
        self.Bind(wx.EVT_UPDATE_UI, self._on_update_ui)
        # Skip()ped in the handler: the control keeps its own focus handling.
        self.ctrl.Bind(wx.EVT_SET_FOCUS, self._on_focus_change)
        self.ctrl.Bind(wx.EVT_KILL_FOCUS, self._on_focus_change)
        self._layout_ctrl()

    # -- geometry ---------------------------------------------------------

    def DoGetBestSize(self) -> wx.Size:  # noqa: N802 - wx override
        """The child's best size, **not** the child's plus the border.

        The border is absorbed into the footprint the field already had rather
        than added to it, so no call site's layout moves: a single-line field
        stays 25px tall and its EDIT client drops 25 -> 21, which still clears
        the 10pt line box with room. Growing instead would have added 4px to
        every field row in the app and moved the enforced minimums phases 3b
        and 6 pinned.
        """
        return self.ctrl.GetBestSize()

    def _layout_ctrl(self) -> None:
        size = self.GetClientSize()
        if size.width <= 0 or size.height <= 0:
            return
        inset = self.FromDIP(INPUT_BORDER_DIP)
        self.ctrl.SetSize(
            inset,
            inset,
            max(0, size.width - 2 * inset),
            max(0, size.height - 2 * inset),
        )

    def _on_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        self._layout_ctrl()
        self.Refresh()

    # -- state ------------------------------------------------------------

    def AcceptsFocusFromKeyboard(self) -> bool:  # noqa: N802 - wx override
        """Delegate to the child; see the module docstring's traversal note."""
        return bool(self._input_enabled and self.ctrl.CanAcceptFocusFromKeyboard())

    def EnableInput(self, enabled: bool = True) -> None:  # noqa: N802 - wx-style API
        """Render the field disabled without letting wxMSW paint it ``#F0F0F0``.

        See the module docstring: ``wx.TextCtrl.Enable(False)`` discards the
        background colour and there is no route back to it.
        """
        self._input_enabled = bool(enabled)
        self.ctrl.SetEditable(self._input_enabled)
        if self._input_enabled:
            stylize_textctrl(self.ctrl, surface=self._surface)
        else:
            self.ctrl.SetBackgroundColour(wx.Colour(*DISABLED_FILL))
            self.ctrl.SetForegroundColour(wx.Colour(*TEXT_DISABLED))
            # A real Enable(False) takes focus and the selection with it. This
            # one cannot, so drop the highlight by hand: otherwise a field that
            # happened to be focused when it was disabled keeps a band of the
            # Windows selection colour (#0078D7) across it.
            self.ctrl.SetSelection(0, 0)
        self.ctrl.Refresh()
        self.Refresh()

    def IsInputEnabled(self) -> bool:  # noqa: N802 - wx-style API
        return self._input_enabled

    def _on_update_ui(self, event: wx.UpdateUIEvent) -> None:
        """Repaint if something called ``Enable``/``Disable`` on the field.

        Same mechanism, and the same reasoning, as
        ``widgets.stylize._watch_enabled_state``: ``Enable`` is a C++ method
        with no event, and ``EVT_UPDATE_UI`` already fires each idle cycle
        whether or not a handler is bound.
        """
        event.Skip()
        current = bool(self.ctrl.IsEnabled())
        if current != self._last_enabled:
            self._last_enabled = current
            self.Refresh()

    def _on_focus_change(self, event: wx.FocusEvent) -> None:
        event.Skip()
        # Deferred: HasFocus() may still report the pre-transition state.
        wx.CallAfter(self._refresh_if_alive)

    def _refresh_if_alive(self) -> None:
        if self:  # the frame may have been destroyed before the CallAfter ran
            self.Refresh()

    # -- painting ---------------------------------------------------------

    def _on_paint(self, _event: wx.PaintEvent) -> None:
        dc = wx.AutoBufferedPaintDC(self)
        enabled = self._input_enabled and self.ctrl.IsEnabled()
        paint_input_border(
            self,
            dc,
            enabled=enabled,
            focused=self.ctrl.HasFocus(),
            editable=self.ctrl.IsEditable(),
            fill=self.ctrl.GetBackgroundColour(),
        )


def create_text_input(
    parent: wx.Window,
    *,
    level: str | None = None,
    surface: str = "alt",
    placeholder: str | None = None,
    size: wx.Size | tuple[int, int] | None = None,
    **ctrl_kwargs,
) -> InputFrame:
    """Build a bordered text field. Returns the **frame**; the field is ``.ctrl``.

    Add the frame to the sizer and keep the control for everything else::

        field = create_text_input(self, style=wx.TE_PROCESS_ENTER)
        self.date_filter = field.ctrl
        row.Add(field, 1, wx.EXPAND)

    ``size`` applies to the frame, not to the control, so a call site that
    asked for ``(120, -1)`` still occupies 120px; the control fills what is left
    inside the border. ``level``, ``surface`` and ``placeholder`` are handed
    straight to :func:`widgets.stylize.stylize_textctrl`; everything else goes
    to the ``wx.TextCtrl`` constructor.
    """
    frame = InputFrame(parent, surface=surface, **ctrl_kwargs)
    stylize_textctrl(frame.ctrl, level=level, surface=surface, placeholder=placeholder)
    frame.SetBackgroundColour(surface_colour(surface))
    if size is not None:
        frame.SetInitialSize(wx.Size(*size))
    frame._layout_ctrl()
    return frame
