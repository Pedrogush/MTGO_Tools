"""The Match History format / archetype filters, driven on the real window.

The pure filtering rules are pinned in ``tests/test_match_history_metrics.py``,
which runs off-Windows. What that cannot see is the half of the feature that
lives in wx: whether the dropdowns are populated from the parsed history at all,
whether a selection reaches the numbers, and whether the three filters and the
date range narrow *the same* set rather than each replacing the others.

So this builds the real :class:`MatchHistoryFrame` on a stub controller that
returns a fixed history, moves the controls the way a user would, and reads the
labels back. It is a live-tree test in the spirit of
``tests/ui/test_live_widget_audit.py``.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from widgets.frames.match_history.frame import MatchHistoryFrame

USERNAME = "MockPilot"


def _match(
    *,
    opponent: str,
    mtg_format: str,
    our_archetype: str,
    opp_archetype: str,
    day: int,
    won: bool,
) -> dict[str, Any]:
    """One parsed match, in the shape ``parse_gamelog_file`` returns."""
    return {
        "match_id": f"{mtg_format}-{day}",
        "timestamp": datetime(2026, 1, day, 12, 0),
        "players": [USERNAME, opponent],
        "opponent": opponent,
        "winner": USERNAME if won else opponent,
        "match_score": "2-0" if won else "0-2",
        "games": [],
        "format": mtg_format,
        "player1_deck": [],
        "player2_deck": [],
        "player1_archetype": our_archetype,
        "player2_archetype": opp_archetype,
        "player1_mulligans": [1, 0],
        "player2_mulligans": [0, 0],
        "total_mulligans": 1,
    }


#: Four matches chosen so every filter dimension separates them differently:
#: two formats, two decks of ours, two decks of theirs, two dates.
HISTORY = [
    _match(
        opponent="alice",
        mtg_format="Modern",
        our_archetype="Burn",
        opp_archetype="Tron",
        day=1,
        won=True,
    ),
    _match(
        opponent="bob",
        mtg_format="Modern",
        our_archetype="Burn",
        opp_archetype="Murktide",
        day=2,
        won=False,
    ),
    _match(
        opponent="carol",
        mtg_format="Pauper",
        our_archetype="Familiars",
        opp_archetype="Burn",
        day=3,
        won=True,
    ),
    _match(
        opponent="dave",
        mtg_format="Pauper",
        our_archetype="Familiars",
        opp_archetype="Burn",
        day=4,
        won=True,
    ),
]


class _StubController:
    """The three calls ``MatchHistoryFrame`` makes on its controller."""

    def get_current_username(self) -> str:
        return USERNAME

    def parse_all_gamelogs(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return [dict(match) for match in HISTORY]

    def infer_username_from_matches(self, _matches: list[dict[str, Any]]) -> str:
        return USERNAME


@pytest.fixture(name="frame")
def fixture_frame(wx_app: wx.App) -> Iterator[MatchHistoryFrame]:
    frame = MatchHistoryFrame(controller=_StubController())
    frame.Show()
    # The history is loaded on a worker thread and applied through wx.CallAfter,
    # so the queue has to drain before anything is on screen.
    for _ in range(40):
        pump_ui_events(wx_app)
        if frame.history_items:
            break
    try:
        yield frame
    finally:
        frame.Destroy()
        pump_ui_events(wx_app)


def _select(frame: MatchHistoryFrame, choice: wx.Choice, value: str) -> None:
    """Pick *value* and fire the same event a click would."""
    index = choice.FindString(value)
    assert index != wx.NOT_FOUND, f"{value!r} is not offered; got {choice.GetStrings()}"
    choice.SetSelection(index)
    frame._on_filter_changed(None)


def test_the_history_actually_loaded(frame: MatchHistoryFrame) -> None:
    assert len(frame.history_items) == len(HISTORY)


def test_dropdowns_offer_only_the_values_present_in_the_history(
    frame: MatchHistoryFrame,
) -> None:
    assert frame.format_choice.GetStrings()[1:] == ["Modern", "Pauper"]
    assert frame.our_archetype_choice.GetStrings()[1:] == ["Burn", "Familiars"]
    assert frame.opp_archetype_choice.GetStrings()[1:] == ["Burn", "Murktide", "Tron"]


def test_dropdowns_start_on_the_all_entry(frame: MatchHistoryFrame) -> None:
    for choice in (
        frame.format_choice,
        frame.our_archetype_choice,
        frame.opp_archetype_choice,
    ):
        assert choice.GetSelection() == 0


def test_absolute_rates_cover_the_whole_history(frame: MatchHistoryFrame) -> None:
    assert frame.match_rate_label.GetLabel().startswith("75.0%")
    assert "(3/4)" in frame.match_rate_label.GetLabel()


def test_picking_a_format_narrows_the_filtered_rate_only(frame: MatchHistoryFrame) -> None:
    """The absolute pair is the control: it must not move when a filter does."""
    absolute_before = frame.match_rate_label.GetLabel()
    _select(frame, frame.format_choice, "Pauper")
    assert "(2/2)" in frame.filtered_match_rate_label.GetLabel()
    assert frame.filtered_match_rate_label.GetLabel().startswith("100.0%")
    assert frame.match_rate_label.GetLabel() == absolute_before


def test_picking_our_deck_answers_how_i_do_with_it(frame: MatchHistoryFrame) -> None:
    _select(frame, frame.our_archetype_choice, "Burn")
    assert "(1/2)" in frame.filtered_match_rate_label.GetLabel()


def test_picking_their_deck_answers_how_i_do_against_it(frame: MatchHistoryFrame) -> None:
    """Distinct from the question above: "Burn" is on both sides of this history."""
    _select(frame, frame.opp_archetype_choice, "Burn")
    assert "(2/2)" in frame.filtered_match_rate_label.GetLabel()


def test_format_and_archetype_compose_instead_of_replacing_each_other(
    frame: MatchHistoryFrame,
) -> None:
    _select(frame, frame.format_choice, "Modern")
    _select(frame, frame.our_archetype_choice, "Burn")
    _select(frame, frame.opp_archetype_choice, "Tron")
    assert "(1/1)" in frame.filtered_match_rate_label.GetLabel()


def test_the_date_range_still_composes_with_the_dropdowns(
    frame: MatchHistoryFrame,
) -> None:
    """The regression the shared filter helper exists to prevent."""
    frame.start_date_ctrl.SetValue("2026-01-02")
    frame.end_date_ctrl.SetValue("2026-01-03")
    _select(frame, frame.format_choice, "Pauper")
    assert "(1/1)" in frame.filtered_match_rate_label.GetLabel()


def test_a_selection_with_no_matches_left_reads_as_an_empty_range(
    frame: MatchHistoryFrame,
) -> None:
    _select(frame, frame.format_choice, "Pauper")
    _select(frame, frame.opp_archetype_choice, "Tron")
    assert frame.filtered_match_rate_label.GetLabel() == "—"


def test_the_tree_shows_each_match_s_format(frame: MatchHistoryFrame) -> None:
    """Makes a wrong bucket auditable: the user can see what went into it."""
    tree = frame.tree
    item = tree.GetFirstItem()
    formats = []
    while item.IsOk():
        formats.append(tree.GetItemText(item, 1))
        item = tree.GetNextItem(item)
    assert sorted(formats) == ["Modern", "Modern", "Pauper", "Pauper"]


def test_the_opponent_panel_is_scoped_by_the_filters_too(
    frame: MatchHistoryFrame,
) -> None:
    """Both halves of the panel have to describe the same set of matches."""
    frame._update_opp_stats("carol")
    assert "(1/1)" in frame.opp_match_rate_label.GetLabel()
    _select(frame, frame.format_choice, "Modern")
    frame._update_opp_stats("carol")
    assert frame.opp_match_rate_label.GetLabel() == "—"
