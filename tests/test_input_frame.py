"""The input border's state table, checked against WCAG rather than against a screenshot.

``tests/test_theme_contrast.py`` is the redesign's regression guard for
foreground/background pairs. This is its counterpart for the one *boundary* in
the app that WCAG 1.4.11 actually binds: once phase 6b removed wxMSW's
``#FFFFFF`` client edge, the painted ring is the only thing marking where a
text field is, and phase 0's rule says a sole-marker border must be
``BORDER_STRONG`` (>= 3:1) rather than the decorative ``BORDER_SUBTLE``.

The state table is deliberately a pure function
(:func:`widgets.input_frame.input_border_state`) so this file needs no wx.App:
the decision "which token, how thick" is the reviewable part, and painting it
is not.
"""

from __future__ import annotations

import pytest

from utils.constants.theme import (
    BORDER_STRONG,
    BORDER_SUBTLE,
    DISABLED_BORDER,
    FOCUS_RING,
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    SURFACE_RAISED,
    contrast_ratio,
)
from widgets.input_frame import INPUT_BORDER_DIP, INPUT_BORDER_RESTING_DIP, input_border_state

#: Every surface a bordered field is placed on in the tree today. The ring is
#: painted on the frame, so it is seen against the *parent's* surface.
SURFACES = {
    "base": SURFACE_BASE,
    "panel": SURFACE_PANEL,
    "alt": SURFACE_ALT,
    "raised": SURFACE_RAISED,
}


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_the_resting_border_is_a_sole_marker_border(surface: str) -> None:
    """A field at rest is identified by its ring and by nothing else.

    This is the whole reason phase 6c own-draws: the fill is 1.10:1 on
    ``SURFACE_PANEL``, so the border is not decoration, it is the control's
    boundary -- WCAG 1.4.11's 3:1 case.
    """
    colour, _weight = input_border_state(enabled=True, focused=False, editable=True)
    assert colour == BORDER_STRONG
    ratio = contrast_ratio(colour, SURFACES[surface])
    assert ratio >= 3.0, f"resting input border is {ratio:.2f}:1 on SURFACE_{surface.upper()}"


@pytest.mark.parametrize("surface", sorted(SURFACES))
def test_the_focus_ring_is_visible_on_every_surface(surface: str) -> None:
    colour, _weight = input_border_state(enabled=True, focused=True, editable=True)
    assert colour == FOCUS_RING
    ratio = contrast_ratio(colour, SURFACES[surface])
    assert ratio >= 3.0, f"focus ring is {ratio:.2f}:1 on SURFACE_{surface.upper()}"


def test_focus_changes_both_hue_and_weight() -> None:
    """A field that looks the same focused and unfocused is a regression.

    The native client edge phase 6b removed at least changed on focus. Colour
    alone would be a weaker signal than what it replaced -- and unreadable to
    anyone who cannot separate the two hues -- so the ring also doubles in
    weight. The inset is constant across states, so nothing re-lays-out.
    """
    resting = input_border_state(enabled=True, focused=False, editable=True)
    focused = input_border_state(enabled=True, focused=True, editable=True)
    assert resting[0] != focused[0]
    assert focused[1] > resting[1]
    assert focused[1] == INPUT_BORDER_DIP, "the focus ring fills the frame's whole inset"


def test_focus_beats_read_only_and_disabled_beats_focus() -> None:
    """State precedence, pinned because it is the part that reads wrongly if reordered.

    A read-only field still takes focus, so it must still show the ring (WCAG
    2.4.7). A disabled one cannot be focused at all, so ``disabled`` wins.
    """
    assert input_border_state(enabled=True, focused=True, editable=False)[0] == FOCUS_RING
    assert input_border_state(enabled=False, focused=True, editable=True)[0] == DISABLED_BORDER


def test_read_only_and_disabled_use_the_decorative_token() -> None:
    """``BORDER_SUBTLE`` is below 3:1 by design and that is correct here.

    WCAG 1.4.11 exempts inactive components, and applies to boundaries required
    to identify a control you can *act* on. A read-only field is not an input
    target; a disabled one is inactive. Using ``BORDER_STRONG`` for either would
    make the two states in the app that cannot be typed into as loud as the
    twelve that can.
    """
    assert input_border_state(enabled=True, focused=False, editable=False) == (
        BORDER_SUBTLE,
        INPUT_BORDER_RESTING_DIP,
    )
    assert input_border_state(enabled=False, focused=False, editable=True) == (
        DISABLED_BORDER,
        INPUT_BORDER_RESTING_DIP,
    )
