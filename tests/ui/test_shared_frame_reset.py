"""The contract ``shared_frame`` offers: every test starts from the same window.

One ``AppFrame`` serves a whole module, so what a test leaves behind is what the
next one starts with unless :meth:`SharedAppFrame.reset` puts it back. Nothing
enforced that. The state the reset missed -- the archetype list and its
selection, the window's size, the card views' mode, and the debounce timers that
live on panels rather than on the frame -- happened to be state the existing
files either re-established themselves (every test in
``test_card_view_scroll_snap`` re-applies the floor; every archetype test calls
``fetch_archetypes`` first) or never read. The suite was green and
order-dependent at the same time, which is the combination that only shows up
the day someone adds the test that reads it.

``tests/README.md`` asks authors to check order independence by hand. This file
is that check, written down: each test asserts one thing about the window it was
handed, then wrecks the window on the way out. Whatever order they run in, all
but the first are reading a window a sibling deliberately dirtied, so the file
cannot go green by being lucky -- and it goes red on the *whole* suite the day
the reset stops covering one of these.
"""

from __future__ import annotations

from typing import Any

import pytest
import wx

from tests.ui.conftest import SharedAppFrame, find_timers, pump_ui_events

#: A mode no card table starts in, so switching to it is always a change.
OTHER_VIEW_MODE = "pile"


def _dirty(frame: Any, wx_app: wx.App) -> None:
    """Leave the window in every state the reset is supposed to undo.

    Each step is the shape of a real test in this suite: loading archetypes and
    picking one is ``test_deck_selector``, sizing the window to its own floor is
    ``test_card_view_scroll_snap``, and a running debounce is any test that
    types into the builder's search box.
    """
    frame.fetch_archetypes()
    pump_ui_events(wx_app)
    frame.research_panel.archetype_list.SetSelection(1)

    frame.main_table.set_view_mode(OTHER_VIEW_MODE, persist=False)
    frame.side_table.set_view_mode(OTHER_VIEW_MODE, persist=False)

    frame._apply_min_size()
    frame.SetSize(frame.GetMinSize())
    frame.Layout()
    pump_ui_events(wx_app)

    # Long enough that none of them can fire during the run: what is being
    # pinned is that the reset stops them, not what their handlers do.
    for timer in find_timers(frame):
        timer.Start(60_000, oneShot=True)


def test_the_archetype_list_and_its_selection_are_put_back(
    shared_frame: Any, wx_app: wx.App
) -> None:
    """A window with no deck loaded must not still be pointing at an archetype.

    ``_baseline_archetype`` falls back to the research selection, and the reset
    has just emptied the loaded deck -- so a leftover selection makes the
    Baseline tab measure a pool the test never chose.
    """
    combo = shared_frame.research_panel.archetype_list

    assert shared_frame.controller.archetypes == []
    assert shared_frame.controller.filtered_archetypes == []
    assert combo.GetStrings() == []
    assert combo.GetSelection() == wx.NOT_FOUND
    assert shared_frame._baseline_archetype() is None

    _dirty(shared_frame, wx_app)


def test_the_window_is_back_at_its_own_size(
    shared_app_frame: SharedAppFrame, shared_frame: Any, wx_app: wx.App
) -> None:
    """Anything that reads a client size reads this one, not the last test's."""
    assert shared_frame.GetSize() == shared_app_frame.size

    _dirty(shared_frame, wx_app)


def test_the_card_views_are_back_in_their_starting_mode(
    shared_app_frame: SharedAppFrame, shared_frame: Any, wx_app: wx.App
) -> None:
    """A zone left showing piles is a different widget than the one a test names."""
    for zone, mode in shared_app_frame.view_modes.items():
        assert getattr(shared_frame, f"{zone}_table").view_mode == mode

    _dirty(shared_frame, wx_app)


def test_no_timer_is_left_running_anywhere_in_the_window(shared_frame: Any, wx_app: wx.App) -> None:
    """Including the ones on panels, which is where nearly all of them are.

    A debounce started by one test firing inside the next is the use-after-free
    the fixture's own docstring warns about, one test earlier.
    """
    timers = find_timers(shared_frame)
    owned_by_the_frame = {id(value) for value in vars(shared_frame).values()}
    assert any(id(timer) not in owned_by_the_frame for timer in timers), (
        "the walk only reached the frame's own timers; the builder's debounces "
        "and the card views' marquees are the ones that outlive a test"
    )
    assert [timer for timer in timers if timer.IsRunning()] == []

    _dirty(shared_frame, wx_app)


@pytest.mark.usefixtures("shared_frame")
def test_the_walk_reaches_the_panel_timers_by_name(shared_app_frame: SharedAppFrame) -> None:
    """Named, so a refactor that moves them somewhere the walk misses says so.

    Everything above would still pass if ``find_timers`` quietly stopped
    finding these -- an empty list has nothing running in it.
    """
    frame = shared_app_frame.frame
    reached = {id(timer) for timer in find_timers(frame)}
    expected = {
        "builder search debounce": frame.builder_panel._search_timer,
        "builder prefetch debounce": frame.builder_panel._prefetch_timer,
        "mainboard grid marquee": frame.main_table.grid_view._marquee._timer,
    }
    missing = [name for name, timer in expected.items() if id(timer) not in reached]
    assert not missing, f"find_timers no longer reaches: {missing}"
