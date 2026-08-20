"""Phase 8 — what the window's enforced minimum is allowed to depend on.

``AppFrame._apply_min_size`` takes the root sizer's minimum and pins the frame
to it. That makes every content minimum underneath it load-bearing, and two
things had leaked into it that should never have been able to:

* **the loaded card.** Phase 3b measured the both-panels-expanded floor at 1393
  with one card in the inspector and 1433 with another, because the Stats tab's
  labels are plain ``wx.StaticText`` and a StaticText reports its whole line as
  its best width. Whichever card happened to be showing when ``_apply_min_size``
  last ran set the floor -- a snapshot, correct when taken, not continuously
  true;
* **the deck.** ``wx.grid.Grid.GetBestSize()`` is the grid's entire scrollable
  content, and a ``wx.Simplebook`` takes the max over *all* its pages including
  hidden ones. Visiting the deck workspace's table view once with a 60-card deck
  took the enforced minimum height from 882 to **1461px**, after which the
  window could not be made smaller again -- and the view mode is persisted per
  zone, so leaving the app in table view reproduced it on the next launch.
"""

from __future__ import annotations

import pytest

from tests.ui.conftest import pump_ui_events


@pytest.mark.usefixtures("wx_app")
def test_the_window_floor_does_not_move_with_the_loaded_card(deck_selector_factory, wx_app) -> None:
    frame = deck_selector_factory()
    try:
        pump_ui_events(wx_app)
        frame._apply_min_size()
        before = frame.GetMinSize().Get()

        panel = frame.card_panel
        # Longer than the column is wide, in the level that carries the most
        # weight -- the same shape as the real worst case (a long card name over
        # a long archetype name).
        for label in (
            panel.stats_card_label,
            panel.stats_format_header,
            panel.stats_archetype_header,
        ):
            panel.set_flowing_label(label, "Asmoranomardicadaistinaculdacar of the Ravnica Guilds")
        frame.Layout()
        pump_ui_events(wx_app)
        frame._apply_min_size()

        assert frame.GetMinSize().Get() == before, (
            "the window's floor moved when the inspector's content changed; the "
            "Stats tab is setting the column's width from its text again"
        )
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_window_floor_does_not_move_when_the_table_view_is_visited(
    deck_selector_factory, wx_app
) -> None:
    frame = deck_selector_factory()
    try:
        frame.main_table.set_cards(
            [{"name": "Mountain", "qty": n} for n in range(1, 25)],
        )
        pump_ui_events(wx_app)
        frame._apply_min_size()
        before = frame.GetMinSize().Get()

        for mode in ("table", "pile", "grid"):
            frame.main_table.set_view_mode(mode, persist=False)
            pump_ui_events(wx_app)
        frame.Layout()
        frame._apply_min_size()

        assert frame.GetMinSize().Get() == before, (
            "visiting a view mode moved the window's floor -- a wx.grid.Grid is "
            "reporting its whole scrollable content as a minimum again"
        )
    finally:
        frame.Destroy()
