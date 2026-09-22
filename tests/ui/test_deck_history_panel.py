"""The history tab must not do its reading on the UI thread.

Reading a deck's history is disk work: a blob per commit, out of a git object
store. Done inline it put the whole history on the UI thread on every save,
every deck load and every visit to the tab — measured at over three seconds for
a deck with a hundred versions.

The worker is faked here because it *is* the thread boundary: a real background
thread would make these tests race. Everything on either side of it is real —
a real ``DeckVcsRepository`` on a temp dir, a real panel, a real ``wx.TreeCtrl``
— so what is pinned is which side of the boundary each piece of work lands on.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import wx

from repositories.deck_vcs_repository import DeckVcsRepository
from services.deck_vcs_service import DeckVcsService, HistorySnapshot
from widgets.panels.deck_history_panel import DeckHistoryPanel

DECK_V1 = "4 Lightning Bolt\n2 Consider\n\nSideboard\n2 Abrade\n"
DECK_V2 = "4 Lightning Bolt\n4 Consider\n\nSideboard\n2 Abrade\n"


class RecordingWorker:
    """A worker that holds submissions until a test releases them."""

    def __init__(self) -> None:
        self.submitted: list[tuple[Any, Any, Any]] = []

    def submit(self, func, *args, on_success=None, on_error=None, **kwargs):
        self.submitted.append((func, on_success, on_error))

    def run_next(self) -> None:
        """Run the oldest pending job and deliver its result, as wx would."""
        func, on_success, on_error = self.submitted.pop(0)
        try:
            result = func()
        except Exception as exc:  # noqa: BLE001
            if on_error:
                on_error(exc)
            return
        if on_success:
            on_success(result)


class _DeckRepo:
    """The slice of the deck repository the panel reads."""

    def __init__(self, deck: dict[str, Any] | None) -> None:
        self._deck = deck

    def get_current_deck(self) -> dict[str, Any] | None:
        return self._deck


@pytest.fixture(name="history_panel")
def fixture_history_panel(wx_app, tmp_path: Path):
    """A real panel over a real repo holding two versions of one deck."""
    service = DeckVcsService(vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"))
    service.record_save("mono red", DECK_V1)
    service.record_save("mono red", DECK_V2)

    frame = wx.Frame(None)
    worker = RecordingWorker()
    panel = DeckHistoryPanel(
        frame,
        vcs_service=service,
        deck_repo=_DeckRepo({"deck_name": "mono red"}),
        worker=worker,
    )
    panel.service = service
    panel.worker_double = worker
    yield panel
    frame.Destroy()


@pytest.mark.usefixtures("wx_app")
class TestTheHistoryIsReadOffTheUiThread:
    def test_refreshing_submits_the_read_and_paints_nothing_yet(self, history_panel):
        """The UI thread hands the read over; it does not do it."""
        panel = history_panel

        panel.refresh_history()

        assert len(panel.worker_double.submitted) == 1
        assert panel._graph == [], "the graph was read on the UI thread"

    def test_the_answer_paints_the_graph_branches_and_preview(self, history_panel):
        panel = history_panel

        panel.refresh_history()
        panel.worker_double.run_next()

        assert len(panel._graph) == 2
        assert panel.branch_choice.GetStrings() == ["main"]
        assert "Consider" in panel.preview_text.GetValue()
        assert "Consider" in panel.diff_text.GetValue()

    def test_the_work_handed_over_touches_no_wx(self, history_panel):
        """Whatever runs on the worker must be safe to run off the UI thread."""
        panel = history_panel
        panel.refresh_history()
        work, _on_success, _on_error = panel.worker_double.submitted[0]

        snapshot = work()  # called here exactly as the worker thread would

        assert isinstance(snapshot, HistorySnapshot)
        assert len(snapshot.graph) == 2

    def test_a_stale_answer_never_paints_over_a_newer_one(self, history_panel):
        """Two refreshes in flight: the first one back must not win."""
        panel = history_panel
        panel.refresh_history()
        panel.refresh_history()
        first, second = panel.worker_double.submitted

        # The newer read lands first, then the older one arrives late.
        panel.worker_double.submitted = [second, first]
        panel.worker_double.run_next()
        painted = list(panel._graph)

        stale_work, stale_success, _ = panel.worker_double.submitted[0]
        stale_success(HistorySnapshot())

        assert [g.sha for g in panel._graph] == [g.sha for g in painted]
        assert panel._graph != []

    def test_a_broken_history_empties_the_tab_instead_of_raising(self, history_panel):
        panel = history_panel
        panel.refresh_history()
        _work, _on_success, on_error = panel.worker_double.submitted[0]

        on_error(OSError("object store is gone"))

        assert panel._graph == []
        assert panel.preview_text.GetValue() == ""

    def test_without_a_worker_it_reads_inline(self, wx_app, tmp_path: Path):
        """Tests and standalone panels have no worker and must still work."""
        service = DeckVcsService(vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"))
        service.record_save("mono red", DECK_V1)
        frame = wx.Frame(None)
        try:
            panel = DeckHistoryPanel(
                frame,
                vcs_service=service,
                deck_repo=_DeckRepo({"deck_name": "mono red"}),
                worker=None,
            )
            panel.refresh_history()
            assert len(panel._graph) == 1
        finally:
            frame.Destroy()


@pytest.mark.usefixtures("wx_app")
class TestTheGraphIsPaintedInOneGo:
    def test_the_panel_is_frozen_while_the_graph_is_applied(self, history_panel):
        """Unfrozen, every canvas and field write repaints on its own."""
        panel = history_panel
        panel.refresh_history()

        events: list[str] = []
        panel.Freeze = lambda: events.append("freeze")  # type: ignore[method-assign]
        panel.Thaw = lambda: events.append("thaw")  # type: ignore[method-assign]
        original_set_layout = panel.graph_canvas.set_layout

        def spy(layout):
            events.append("paint")
            return original_set_layout(layout)

        panel.graph_canvas.set_layout = spy  # type: ignore[method-assign]
        panel.worker_double.run_next()

        assert events == ["freeze", "paint", "thaw"]
