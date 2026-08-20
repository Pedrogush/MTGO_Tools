"""#983: dragging the mainboard/sideboard sash smears the edge fade.

What broke
----------
The redesign's S5 fade (:mod:`widgets.panels.card_table_panel.edge_fade`) is the
only thing the card views paint against the **viewport** rather than against the
content: a 24px band hugging whichever pane edge has content past it. Everything
else they draw is a blit out of a content-sized canvas, so it stays correct
wherever the window's pixels end up.

wxMSW invalidates only the **newly exposed** strip of a resized window, and a
``wx.PaintDC`` is clipped to the update region by ``BeginPaint``. Measured in the
running app while the sash was dragged, with the update region logged from the
view's own paint handler::

    region=(0, 307, 549, 15)  client=(549, 322)
    region=(0, 322, 549, 15)  client=(549, 337)
    region=(0, 337, 549, 15)  client=(549, 352)

-- one 15px strip per step, at the bottom of a pane that is growing 15px per
step, and *no paint at all* for the pane that is shrinking. So each paint drew
the fade against the new bottom edge and left the previous paint's fade in the
retained pixels above it. A live sash drag (``SP_LIVE_UPDATE``) resizes the panes
once per mouse-move, so the band the edge sweeps past collects one 24px fade per
step: the dark horizontal stripes smeared across the card rows that were
reported. Screen-pixel capture of a 300px drag before the fix differed from a
forced full re-render over 25% of the deck workspace; after it, by zero pixels.

What is pinned
--------------
That a resize of a card view asks for a repaint of the **whole client**, every
time and in both directions, rather than trusting whatever region wx invalidated.
That is the contract the fade needs and the one that was missing; the grid only
repainted when the *column count* changed (which a vertical drag never does) and
the pile view did not handle ``EVT_SIZE`` at all.

It is asserted on the request rather than on the resulting pixels deliberately.
The size of the region wx *itself* invalidates turns out to depend on whether the
window is unoccluded on screen -- an occluded window has no preserved pixels, so
MSW invalidates all of it and the bug hides -- which is exactly the kind of
"passes on the machine that cannot see the bug" test this suite already warns
about. What the view asks for does not vary with any of that.

Every assertion is pinned against a vacuous pass the same way
``test_card_view_scroll_snap`` is: each step asserts that the view really
resized before it asserts what the view asked for.
"""

from __future__ import annotations

import pytest
import wx

from tests.ui.conftest import pump_ui_events

#: Enough distinct cards that both zones are several rows deep at the frame's
#: enforced floor, so both views really do have a clipped edge to fade.
_DECK = [
    "Blazing Rootwalla",
    "Marauding Mako",
    "Hardened Academic",
    "Vengevine",
    "Hollow One",
    "Street Wraith",
    "Burning Inquiry",
    "Faithless Looting",
    "Lightning Bolt",
    "Arid Mesa",
    "Bloodstained Mire",
    "Mountain",
    "Scalding Tarn",
    "Sacred Foundry",
    "Wooded Foothills",
    "Practiced Offense",
    "Prismatic Ending",
    "Vexing Bauble",
    "Damping Sphere",
]

#: Pixels of sash travel per step. Smaller than the 24px fade band, which is what
#: makes the stale bands overlap into a solid smear rather than read as stripes.
_DRAG_STEP_PX = 15


def _deck_tables_frame(deck_selector_factory, wx_app):
    """A frame at its own enforced floor with the Deck Tables split in front."""
    frame = deck_selector_factory()
    frame.main_table.set_cards([{"name": name, "qty": 4} for name in _DECK])
    frame.side_table.set_cards([{"name": name, "qty": 2} for name in _DECK])
    pump_ui_events(wx_app)
    frame._apply_min_size()
    frame.SetSize(frame.GetMinSize())
    # The split has to be the visible page or its panes are never laid out.
    for index in range(frame.deck_tabs.GetPageCount()):
        if frame.deck_tabs.GetPage(index) is frame.deck_split:
            frame.deck_tabs.SetSelection(index)
            break
    frame.Layout()
    pump_ui_events(wx_app)
    return frame


def _view(frame, zone: str, mode: str):
    table = getattr(frame, f"{zone}_table")
    table.set_view_mode(mode, persist=False)
    return getattr(table, "pile_view" if mode == "pile" else "grid_view")


def _sash_range(splitter: wx.SplitterWindow) -> tuple[int, int]:
    minimum = splitter.GetMinimumPaneSize()
    return minimum, splitter.GetClientSize().GetHeight() - minimum - splitter.GetSashSize()


@pytest.mark.parametrize("zone", ["main", "side"])
@pytest.mark.parametrize("mode", ["grid", "pile"])
@pytest.mark.usefixtures("wx_app")
def test_a_sash_drag_repaints_the_whole_card_view(
    deck_selector_factory, wx_app, monkeypatch, zone, mode
) -> None:
    """Every step of a sash drag asks the resized view for a full repaint (#983).

    Anything less leaves the previous step's edge fade on screen at the edge the
    pane no longer has, which is the smear.
    """
    frame = _deck_tables_frame(deck_selector_factory, wx_app)
    try:
        view = _view(frame, zone, mode)
        splitter = frame.deck_split
        low, high = _sash_range(splitter)
        assert high - low > 4 * _DRAG_STEP_PX, (
            f"the split has no room to drag in (sash range {low}..{high}); "
            "the frame is not laid out, so this test would prove nothing"
        )

        requested: list[tuple[bool, wx.Rect | None]] = []
        monkeypatch.setattr(
            view,
            "Refresh",
            lambda eraseBackground=True, rect=None: requested.append((eraseBackground, rect)),
        )

        splitter.SetSashPosition(high)
        pump_ui_events(wx_app)

        # Down and back up: one leg grows this pane and the other shrinks it,
        # and before the fix the two failed differently -- a partial strip, and
        # no repaint at all.
        position = high
        heights: list[int] = []
        for target in (low, high):
            while position != target:
                step = min(_DRAG_STEP_PX, abs(target - position))
                position += step if target > position else -step
                requested.clear()
                splitter.SetSashPosition(position)
                height = view.GetClientSize().GetHeight()
                assert heights[-1:] != [height], (
                    f"the {zone} {mode} view did not resize when the sash moved to "
                    f"{position} (still {height}px); this step proves nothing"
                )
                heights.append(height)
                assert requested, (
                    f"the {zone} {mode} view was not asked to repaint when the sash "
                    f"moved to {position}: wxMSW invalidates only the strip it just "
                    "exposed, so the edge fade stays painted at the old edge"
                )
                assert all(rect is None for _erase, rect in requested), (
                    f"the {zone} {mode} view asked to repaint only {requested}; the "
                    "fade sits at whichever edge the pane now has, so a partial "
                    "repaint is what smears it"
                )

        assert len(set(heights)) > 4, (
            f"the {zone} {mode} view barely resized during the drag "
            f"(heights seen: {sorted(set(heights))})"
        )
    finally:
        frame.Destroy()
