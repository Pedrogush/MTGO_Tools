"""The phase 6b audit, run against a **real** widget tree.

``tests/test_widget_audit.py`` reads the source. This reads the app. The two
answer different questions and the gap between them is exactly where this
redesign kept losing widgets:

* the static sweep cannot see a widget styled from another module (the deck
  workspace's view toggles are built in ``card_table_panel/frame.py`` and
  stylized in ``card_table_panel/toolbar.py``), so it has to allowlist them --
  and an allowlist is a promise nobody checks;
* it also cannot see a call that *ran* and did nothing, which is this
  codebase's signature failure. Nine instances are documented in
  ``widgets/stylize.py``'s table: colours set on a ``wx.Choice``, a foreground
  set on a ``wx.StatusBar``, ``SetHeaderAttr`` on a ``wx.ListCtrl``. Every one
  of them looked correct in the source.

Walking the live tree closes both. ``stylize_button`` stamps
``_mtgo_button_kind`` on the button it paints, so "did every button in the
running main window reach the button system" is a question the app itself can
answer -- with no allowlist, because indirection is invisible to a tree walk.
"""

from __future__ import annotations

import wx

from utils.constants.theme import TYPE_STEPS, font_point_size
from widgets.input_frame import InputFrame
from widgets.stylize import base_point_size

#: Set on a button by ``stylize_button``; see ``widgets.stylize._BUTTON_KIND_ATTR``.
BUTTON_KIND_ATTR = "_mtgo_button_kind"

#: Live buttons that deliberately do not carry a kind, by label. Exactly one
#: entry, and it is an open question rather than a decision -- see the phase 6b
#: report.
UNSTYLED_BY_LABEL: dict[str, str] = {
    "\u25c0": (
        "The two panel collapse toggles. Phase 6 stripped wxMSW's light frame "
        "from them but never routed them through stylize_button, so they still "
        "set SURFACE_PANEL and TEXT_PRIMARY by hand. Routing them is blocked on "
        "a decision, not on work: no button kind renders SURFACE_PANEL on a "
        "SURFACE_BASE parent, so every available kind changes what is on screen "
        "-- ``ghost`` steps *up* to SURFACE_ALT and makes two full-height rails "
        "brighter, which is the opposite of what phase 6 was fixing, and "
        "``flat`` makes them vanish into the background and would want a hover "
        "state to stay discoverable. Measured today: a 16px SURFACE_PANEL rail "
        "at 1.32:1 on SURFACE_BASE."
    ),
}


def _walk(window: wx.Window):
    yield window
    for child in window.GetChildren():
        yield from _walk(child)


def _describe(window: wx.Window) -> str:
    label = ""
    if hasattr(window, "GetLabel"):
        try:
            label = window.GetLabel()
        except Exception:  # pragma: no cover - some controls have no label
            label = ""
    return f"{type(window).__name__}({label!r})"


def test_every_live_button_carries_a_button_kind(deck_selector_factory) -> None:
    """No wx.Button in the running main window escaped ``stylize_button``.

    An uncoloured ``wx.Button`` renders in wxMSW's *light* system face even
    under process dark mode, inside a 2px ``#ADADAD``/``#E1E1E1`` frame -- so
    "no kind" is not a neutral state, it is a light widget. ``wx.BitmapButton``
    and ``wx.ToggleButton`` subclass ``wx.Button``, so this reaches all three.
    """
    frame = deck_selector_factory()
    try:
        offenders = [
            _describe(w)
            for w in _walk(frame)
            if isinstance(w, wx.Button)
            and not hasattr(w, BUTTON_KIND_ATTR)
            and w.GetLabel() not in UNSTYLED_BY_LABEL
        ]
        assert offenders == [], (
            "these live buttons never reached stylize_button, so wxMSW is "
            f"drawing them in the light system face: {offenders}"
        )
    finally:
        frame.Destroy()


# There is deliberately no "no live widget is near-white" test here, and the
# reason is a wx behaviour worth writing down rather than a gap:
# **``GetBackgroundColour()`` cannot tell you what a widget is painted.** A
# child that has never had one set reports ``#F0F0F0`` -- the system default --
# whatever its parent is, and ``InheritsBackgroundColour()`` returns ``False``
# for it too, so wx exposes no way to distinguish "explicitly light" from
# "inherits the dark parent it is drawn on". A first draft of this file asserted
# on that value and produced 47 offenders, every one of them a widget that
# renders dark on screen. That is precisely the guard the brief warns against:
# broad, wrong, and quickly ignored. The palette is covered statically instead,
# by ``tests/test_widget_audit.py``'s colour-literal sweep.


def test_every_live_font_size_is_on_the_type_ladder(deck_selector_factory) -> None:
    """Phase 3's ladder, verified where it actually lands.

    Font inheritance is a construction-time mechanism (see
    ``widgets.stylize.apply_base_font``), so whether a widget ended up on the
    ladder depends on the order its parents were built in -- something no
    amount of source reading settles. The mana rich-text control passed every
    static check and still reported 9pt, because it asked
    ``wx.SystemSettings`` for a font after its parent had been raised to 10pt.
    """
    frame = deck_selector_factory()
    try:
        allowed = {font_point_size(base_point_size(), level) for level in TYPE_STEPS}
        offenders = []
        for window in _walk(frame):
            font = window.GetFont()
            if not font.IsOk():
                continue
            if int(font.GetPointSize()) not in allowed:
                offenders.append(f"{_describe(window)} -> {font.GetPointSize()}pt")
        assert offenders == [], f"font sizes off the ladder {sorted(allowed)}: {offenders}"
    finally:
        frame.Destroy()


def test_every_live_text_input_sits_inside_an_input_frame(deck_selector_factory) -> None:
    """Phase 6c's border, checked where the static guard cannot reach.

    ``tests/test_widget_audit.py`` bans a bare ``wx.TextCtrl(`` in the source.
    That is the right guard for the construction site and it is blind to two
    things a tree walk is not: a field built by a library or a helper outside
    ``widgets/``, and a field whose frame was constructed but never made its
    parent -- which is exactly the mistake the API invites, because the call
    site holds a reference to the *control* and hands the *frame* to the sizer.
    Getting that backwards leaves a field that works perfectly and has no
    border, and no static check can tell.

    ``wx.SearchCtrl`` subclasses ``wx.TextCtrl``; the app has none today, and if
    one appears it is a text input and belongs in a frame like the rest.
    """
    frame = deck_selector_factory()
    try:
        inputs = [w for w in _walk(frame) if isinstance(w, wx.TextCtrl)]
        # Pinned for the same reason test_the_sweep_actually_sees_the_tree is:
        # a walk that stops finding text inputs passes silently forever. The
        # main window carries six (research: date, placement value, player
        # name; builder: card name, type line, mana value), and only one of the
        # two panels is built at a time.
        assert len(inputs) >= 3, f"the walk found only {len(inputs)} text inputs"
        offenders = [_describe(w) for w in inputs if not isinstance(w.GetParent(), InputFrame)]
        assert offenders == [], (
            "these live text inputs are not hosted by an InputFrame, so they "
            "render as a 1.10:1 fill with no boundary: " + str(offenders)
        )
    finally:
        frame.Destroy()
