"""The version rail beside the deck tables, and what a click on it means.

The rail exists so moving between versions does not cost a trip out to the
History tab and back, which makes two things load-bearing: it must show the same
versions the tab does without reading them again, and a click on a node must
*be* the move rather than the start of one.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import wx

from repositories.deck_vcs_repository import DeckVcsRepository
from services.deck_vcs_service import DeckVcsService, HistorySnapshot
from tests.ui.conftest import wait_until
from widgets.panels.deck_history_rail import DeckHistoryRail
from widgets.panels.deck_history_rail.canvas import ROW_HEIGHT

DECK_V1 = "4 Lightning Bolt\n2 Consider\n\nSideboard\n2 Abrade\n"
DECK_V2 = "4 Lightning Bolt\n4 Consider\n\nSideboard\n2 Abrade\n"
DECK_V3 = "4 Lightning Bolt\n4 Consider\n1 Fable of the Mirror-Breaker\n\nSideboard\n2 Abrade\n"


@pytest.fixture(name="history")
def fixture_history(tmp_path: Path) -> HistorySnapshot:
    """Three real versions of one deck, read the way the frame reads them."""
    service = DeckVcsService(vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"))
    for text in (DECK_V1, DECK_V2, DECK_V3):
        service.record_save("mono red", text)
    return service.read_history("mono red")


@pytest.fixture(name="rail")
def fixture_rail(wx_app):
    frame = wx.Frame(None, size=(400, 600))
    checked_out: list[str] = []
    rail = DeckHistoryRail(frame, on_checkout=checked_out.append)
    rail.checked_out = checked_out
    frame.Show()
    # The rail measures itself off a real client size, so wait for the window
    # to have one rather than guessing at a number of yields (tests/README.md).
    wait_until(
        wx_app,
        lambda: frame.IsShown() and rail.canvas.GetClientSize().GetWidth() > 0,
        message="the history rail never got a client size to draw into",
    )
    yield rail
    frame.Destroy()


def _click_row(rail, row: int) -> None:
    """Click the node on ``row`` of the rail's canvas."""
    canvas = rail.canvas
    point = wx.Point(canvas.GetClientSize().GetWidth() // 2, row * ROW_HEIGHT + ROW_HEIGHT // 2)
    event = wx.MouseEvent(wx.wxEVT_LEFT_DOWN)
    event.SetPosition(point)
    canvas._on_left_down(event)


@pytest.mark.usefixtures("wx_app")
class TestTheRailShowsWhatTheTabShows:
    def test_it_paints_the_snapshot_it_is_given(self, rail, history):
        rail.set_snapshot(history)

        assert len(rail.canvas._layout.nodes) == 3

    def test_it_reads_nothing_of_its_own(self, rail, history):
        """Its whole cost is a repaint; the history was read once, elsewhere."""
        rail.set_snapshot(history)

        # Nothing on the rail can reach a repository or a service.
        assert not hasattr(rail, "vcs_service")
        assert not hasattr(rail.canvas, "vcs_service")

    def test_it_marks_the_version_the_deck_is_on(self, rail, history):
        rail.set_snapshot(history)

        head = next(g.sha for g in history.graph if g.commit.is_head)
        assert rail.canvas.head_sha == head

    def test_it_names_the_branch(self, rail, history):
        rail.set_snapshot(history)

        assert rail.branch_label.GetLabel() == "main"

    def test_a_long_branch_name_ellipsises_instead_of_widening_the_strip(self, rail, history):
        """Branch names are user-supplied; the strip's width is not negotiable."""
        wide = HistorySnapshot(
            graph=history.graph,
            branches=history.branches,
            current_branch="branch-from-7e31e5b-experiments-with-the-mana-base",
            preview=history.preview,
        )
        before = rail.GetMinSize().GetWidth()

        rail.set_snapshot(wide)

        style = rail.branch_label.GetWindowStyleFlag()
        assert style & wx.ST_ELLIPSIZE_END
        assert style & wx.ST_NO_AUTORESIZE
        assert rail.branch_label.GetMinSize().GetWidth() == 0
        assert rail.GetMinSize().GetWidth() == before

    def test_a_deck_with_no_history_empties_it(self, rail, history):
        rail.set_snapshot(history)
        rail.set_snapshot(HistorySnapshot())

        assert rail.canvas._layout.nodes == ()
        assert rail.canvas.head_sha is None
        assert not rail.branch_label.IsShown()

    def test_it_keeps_its_width_whatever_it_shows(self, rail, history):
        """It is a strip cut out of the card tables, so it may not creep."""
        before = rail.GetMinSize().GetWidth()
        rail.set_snapshot(history)

        assert rail.GetMinSize().GetWidth() == before
        assert rail.GetMaxSize().GetWidth() == before


@pytest.mark.usefixtures("wx_app")
class TestClickingANodeIsTheMove:
    def test_a_click_checks_that_version_out(self, rail, history):
        rail.set_snapshot(history)

        _click_row(rail, 2)  # the oldest version, at the bottom

        oldest = history.graph[-1].sha
        assert rail.checked_out == [oldest]

    def test_no_dialog_stands_between_the_click_and_the_move(self, rail, history, monkeypatch):
        """The whole point of the rail is that a move costs one click."""
        rail.set_snapshot(history)
        asked: list[object] = []
        monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: asked.append(a))

        _click_row(rail, 1)

        assert asked == []
        assert len(rail.checked_out) == 1

    def test_clicking_the_version_already_loaded_does_nothing(self, rail, history):
        """A checkout of HEAD rewrites the user's file to say what it says."""
        rail.set_snapshot(history)

        _click_row(rail, 0)  # HEAD is the newest, at the top

        assert rail.checked_out == []

    def test_clicking_past_the_last_node_does_nothing(self, rail, history):
        rail.set_snapshot(history)

        _click_row(rail, 9)

        assert rail.checked_out == []
