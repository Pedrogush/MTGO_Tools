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


@pytest.mark.usefixtures("wx_app")
class TestLoadingADeckRefreshesTheOpenTab:
    """A deck load has to reach the tabs that read more than the decklist.

    Notes, Stats and the Sideboard Guide are refreshed by the load itself. The
    History tab was not: it was repainted only by the file-dialog path, so a
    deck opened from Research left it showing the *previous* deck's commits
    while its header named the new one.
    """

    @staticmethod
    def _history_panel_over(frame, tmp_path):
        """Point the frame's History tab at a repo holding two decks."""
        service = DeckVcsService(vcs_repo=DeckVcsRepository(tmp_path / "deck_vcs"))
        service.record_save("first deck", DECK_V1)
        service.record_save("first deck", DECK_V2)
        service.record_save("second deck", DECK_V1)

        panel = frame.deck_history_panel
        panel.vcs_service = service
        # Inline, so the assertion reads the answer rather than a race.
        panel.worker = None
        # ``shared_frame`` hands back one panel per module, so clear what an
        # earlier test painted -- these assert on what a load *did*, which is
        # only readable against a known starting state.
        panel._graph = []
        panel._last_deck_key = None
        panel._selected_sha = None
        return panel

    @staticmethod
    def _open_history_tab(frame) -> None:
        tabs = frame.deck_tabs
        for index in range(tabs.GetPageCount()):
            if tabs.GetPage(index) is frame.deck_history_panel:
                tabs.SetSelection(index)
                return
        raise AssertionError("the History tab is not in the deck notebook")

    def test_a_deck_opened_from_research_repaints_the_graph(self, shared_frame, tmp_path):
        frame = shared_frame
        panel = self._history_panel_over(frame, tmp_path)
        self._open_history_tab(frame)

        frame.controller.deck_repo.set_current_deck({"deck_name": "first deck"})
        panel.refresh_history()
        assert len(panel._graph) == 2

        # A deck arriving from anywhere -- Research, an average, the clipboard --
        # lands in _on_deck_content_ready, which is the path that was missing.
        frame.controller.deck_repo.set_current_deck({"deck_name": "second deck"})
        frame._on_deck_content_ready(DECK_V1, source="mtggoldfish")

        assert len(panel._graph) == 1, "the graph still shows the previous deck"

    def test_the_tab_header_and_the_graph_name_the_same_deck(self, shared_frame, tmp_path):
        frame = shared_frame
        panel = self._history_panel_over(frame, tmp_path)
        self._open_history_tab(frame)

        frame.controller.deck_repo.set_current_deck({"deck_name": "first deck"})
        panel.refresh_history()
        frame.controller.deck_repo.set_current_deck({"deck_name": "second deck"})
        frame._on_deck_content_ready(DECK_V1, source="file")

        assert panel.current_deck_key() == "second deck"
        assert len(panel._graph) == 1

    def test_the_history_is_read_even_with_the_tab_hidden(self, shared_frame, tmp_path):
        """The rail beside the deck tables shows it, and the rail is never hidden.

        The tab being closed is no longer a reason to skip the read: something
        on screen is always showing this deck's versions.
        """
        frame = shared_frame
        panel = self._history_panel_over(frame, tmp_path)
        tabs = frame.deck_tabs
        tabs.SetSelection(0)  # the deck tables, not History
        assert tabs.GetPage(tabs.GetSelection()) is not panel

        frame.controller.deck_repo.set_current_deck({"deck_name": "first deck"})
        frame._on_deck_content_ready(DECK_V1, source="file")

        assert len(panel._graph) == 2

    def test_the_history_is_read_once_per_load_not_twice(self, shared_frame, tmp_path):
        """The tab is refreshed by the load; waking it again would repeat it."""
        frame = shared_frame
        panel = self._history_panel_over(frame, tmp_path)
        self._open_history_tab(frame)

        reads: list[str] = []
        original = panel.vcs_service.read_history

        def counting(deck_key, **kwargs):
            reads.append(deck_key)
            return original(deck_key, **kwargs)

        panel.vcs_service.read_history = counting  # type: ignore[method-assign]
        frame.controller.deck_repo.set_current_deck({"deck_name": "first deck"})
        frame._on_deck_content_ready(DECK_V1, source="file")

        assert reads == ["first deck"]


@pytest.mark.usefixtures("wx_app")
class TestCheckingOutDoesNotAskFirst:
    """Moving between versions is the feature, so it costs one action.

    It used to raise a yes/no modal on every checkout, warning that the deck
    file would be rewritten. What that protects against is thin: the version
    being left is still a node on the graph, so the move is undone by making the
    opposite one. What it cost was doubling the price of the thing the whole
    view exists to do.
    """

    def test_no_dialog_stands_between_the_action_and_the_move(
        self, history_panel, tmp_path, monkeypatch
    ):
        panel = history_panel
        panel.refresh_history()
        panel.worker_double.run_next()
        oldest = panel._graph[-1].sha

        asked: list[object] = []
        monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: asked.append(a))
        panel.checkout_version(oldest)

        assert asked == [], "a confirmation was raised"

    def test_the_deck_actually_moves(self, history_panel):
        panel = history_panel
        panel.refresh_history()
        panel.worker_double.run_next()
        oldest = panel._graph[-1].sha

        loaded: list[str] = []
        panel._on_checkout = loaded.append
        panel.checkout_version(oldest)

        assert len(loaded) == 1
        assert "2 Consider" in loaded[0], "the older version's decklist came back"

    def test_a_failed_checkout_still_reports(self, history_panel, monkeypatch):
        """Dropping the confirmation must not drop the error path with it."""
        panel = history_panel
        panel.refresh_history()
        panel.worker_double.run_next()

        def boom(*_args, **_kwargs):
            raise OSError("the deck file is read-only")

        monkeypatch.setattr(panel.vcs_service, "checkout", boom)
        shown: list[object] = []
        monkeypatch.setattr(wx, "MessageBox", lambda *a, **k: shown.append(a))
        panel.checkout_version(panel._graph[-1].sha)

        assert len(shown) == 1
