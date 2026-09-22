"""The Baseline tab's rendering cost, which is wx's and not the analysis's.

The computation was always on the background worker. What was not was drawing
it: a visible ``wx.TreeCtrl`` lays out and repaints on every ``AppendItem`` and
every ``Expand``, and this tree routinely runs to a hundred rows. Measured on a
real stored baseline it was 318 ms unfrozen against 17 ms frozen — so freezing
is the whole difference between the tab opening and the tab stuttering.
"""

from __future__ import annotations

import pytest
import wx

from services.archetype_baseline_service.models import (
    ArchetypeBaseline,
    BaselineCard,
    CardFrequency,
    CardRole,
    FlexCandidate,
    ZoneShape,
)
from widgets.panels.deck_baseline_panel import DeckBaselinePanel


def _card(name: str, role: CardRole, count: float) -> BaselineCard:
    return BaselineCard(
        name=name,
        is_sideboard=False,
        role=role,
        fixed_count=count,
        frequency=CardFrequency(
            name=name,
            is_sideboard=False,
            decks_with=10,
            pool_size=10,
            counts={count: 10},
        ),
    )


def _baseline() -> ArchetypeBaseline:
    """A baseline the size the tab really renders: dozens of rows."""
    staples = [_card(f"Staple {i}", CardRole.STAPLE, 4) for i in range(12)]
    partials = [_card(f"Partial {i}", CardRole.PARTIAL_STAPLE, 2) for i in range(10)]
    flex = tuple(
        FlexCandidate(
            name=f"Flex {i}",
            is_sideboard=False,
            play_rate=0.4,
            average_count=1.5,
            above_floor=False,
        )
        for i in range(40)
    )
    return ArchetypeBaseline(
        archetype="Boros Energy",
        mtg_format="Modern",
        pool_size=10,
        cards=tuple(staples + partials),
        flex_candidates=flex,
        main=ZoneShape(size=60.0, fixed=48.0),
        sideboard=ZoneShape(size=15.0, fixed=7.0),
        sources=tuple(str(i) for i in range(10)),
    )


@pytest.fixture(name="baseline_panel")
def fixture_baseline_panel(wx_app):
    frame = wx.Frame(None)
    panel = DeckBaselinePanel(
        frame,
        worker=None,
        archetype_provider=lambda: {"name": "Boros Energy"},
        format_provider=lambda: "Modern",
    )
    panel._baseline = _baseline()
    yield panel
    frame.Destroy()


@pytest.mark.usefixtures("wx_app")
class TestTheTreeIsBuiltInOneGo:
    def test_the_tree_is_frozen_while_it_is_rebuilt(self, baseline_panel):
        panel = baseline_panel
        events: list[str] = []

        panel.tree.Freeze = lambda: events.append("freeze")  # type: ignore[method-assign]
        panel.tree.Thaw = lambda: events.append("thaw")  # type: ignore[method-assign]
        original = panel.tree.AppendItem

        def spy(*args, **kwargs):
            events.append("append")
            return original(*args, **kwargs)

        panel.tree.AppendItem = spy  # type: ignore[method-assign]
        panel.render()

        assert events[0] == "freeze"
        assert events[-1] == "thaw"
        assert "append" in events

    def test_it_thaws_even_when_rendering_raises(self, baseline_panel):
        """A tree left frozen is a tab that never paints again."""
        panel = baseline_panel
        thawed: list[str] = []
        panel.tree.Thaw = lambda: thawed.append("thaw")  # type: ignore[method-assign]

        def boom(*_args, **_kwargs):
            raise RuntimeError("render blew up")

        panel.tree.AddRoot = boom  # type: ignore[method-assign]

        with pytest.raises(RuntimeError):
            panel.render()

        assert thawed == ["thaw"]

    def test_every_row_still_reaches_the_tree(self, baseline_panel):
        """Freezing must change only when it paints, never what it draws."""
        panel = baseline_panel
        panel.render()

        root = panel.tree.GetRootItem()
        groups = []
        item, cookie = panel.tree.GetFirstChild(root)
        while item.IsOk():
            groups.append(panel.tree.GetChildrenCount(item, False))
            item, cookie = panel.tree.GetNextChild(root, cookie)

        # staples, partial staples, flex — every card in the baseline.
        assert groups == [12, 10, 40]


@pytest.mark.usefixtures("wx_app")
class TestTheTabMeasuresTheDeckOnScreen:
    """Which archetype the tab is about.

    It read the Research list's selection and nothing else, so with a deck of
    that archetype open in front of the player it still said "select an
    archetype in Research" -- a tab in the middle of the workspace asking for a
    second, separate choice when the first one already answered it. Every other
    tab in that notebook describes the deck on screen; so does this one now.
    """

    ARCHETYPES = [
        {"name": "Boros Energy", "href": "boros-energy"},
        {"name": "Amulet Titan", "href": "amulet-titan"},
    ]

    @staticmethod
    def _frame_with_archetypes(frame, archetypes, *, selected_index=0):
        """The research list as the frame really fills it: "Any", then the rest.

        ``selected_index`` is an index into that list, so 0 is "Any" -- which
        is a request for every cached deck, not an archetype.
        """
        frame.controller.archetypes = list(archetypes)
        frame.filtered_archetypes = list(archetypes)
        frame.research_panel.populate_archetypes(["Any"] + [a["name"] for a in archetypes])
        frame.research_panel.archetype_list.SetSelection(selected_index)
        return frame

    def test_a_saved_deck_is_measured_by_the_archetype_it_records(self, shared_frame):
        frame = self._frame_with_archetypes(shared_frame, self.ARCHETYPES)
        frame.controller.deck_repo.set_current_deck(
            {"deck_name": "my boros", "source": "file", "archetype": "Boros Energy"}
        )

        assert frame._baseline_archetype() == self.ARCHETYPES[0]

    def test_a_scraped_deck_is_measured_by_the_slug_it_carries(self, shared_frame):
        """A research deck holds its archetype's slug in ``name``."""
        frame = self._frame_with_archetypes(shared_frame, self.ARCHETYPES)
        frame.controller.deck_repo.set_current_deck(
            {"name": "amulet-titan", "source": "mtggoldfish"}
        )

        assert frame._baseline_archetype() == self.ARCHETYPES[1]

    def test_the_deck_wins_over_the_research_selection(self, shared_frame):
        """Both are set and they disagree: the deck in front of the player wins."""
        frame = self._frame_with_archetypes(shared_frame, self.ARCHETYPES, selected_index=2)
        frame.controller.deck_repo.set_current_deck(
            {"deck_name": "my boros", "source": "file", "archetype": "Boros Energy"}
        )

        assert frame._baseline_archetype() == self.ARCHETYPES[0]

    def test_with_no_deck_it_falls_back_to_what_research_is_pointing_at(self, shared_frame):
        """Browsing with nothing loaded is still a reasonable thing to measure."""
        frame = self._frame_with_archetypes(shared_frame, self.ARCHETYPES, selected_index=2)
        frame.controller.deck_repo.set_current_deck(None)

        assert frame._baseline_archetype() == self.ARCHETYPES[1]

    def test_an_archetype_outside_the_format_reads_as_unresolved(self, shared_frame):
        """No entry means no pool, so it is not offered as a target."""
        frame = self._frame_with_archetypes(shared_frame, self.ARCHETYPES, selected_index=0)
        frame.controller.deck_repo.set_current_deck(
            {"deck_name": "legacy thing", "source": "file", "archetype": "Reanimator"}
        )

        assert frame._baseline_archetype() is None

    def test_a_deck_with_no_archetype_at_all_reads_as_unresolved(self, shared_frame):
        frame = self._frame_with_archetypes(shared_frame, self.ARCHETYPES, selected_index=0)
        frame.controller.deck_repo.set_current_deck({"deck_name": "brew", "source": "file"})

        assert frame._baseline_archetype() is None


@pytest.mark.usefixtures("wx_app")
class TestTheTreeNeverDescribesTheWrongArchetype:
    """The target moves with the deck, so what is drawn can go out of date."""

    def test_switching_archetype_clears_the_previous_one(self, wx_app):
        target = {"name": "Boros Energy"}
        frame = wx.Frame(None)
        try:
            panel = DeckBaselinePanel(
                frame,
                worker=None,
                archetype_provider=lambda: target,
                format_provider=lambda: "Modern",
            )
            panel._baseline = _baseline()
            panel._computed_for = ("Boros Energy", "Modern")
            panel.render()
            assert panel.tree.GetCount() > 0

            target = {"name": "Amulet Titan"}
            panel.refresh_target()

            assert panel._baseline is None
            assert panel._computed_for is None
            assert panel.tree.GetCount() == 0
        finally:
            frame.Destroy()

    def test_losing_the_archetype_empties_the_tab(self, wx_app):
        target: dict | None = {"name": "Boros Energy"}
        frame = wx.Frame(None)
        try:
            panel = DeckBaselinePanel(
                frame,
                worker=None,
                archetype_provider=lambda: target,
                format_provider=lambda: "Modern",
            )
            panel._baseline = _baseline()
            panel._computed_for = ("Boros Energy", "Modern")
            panel.render()

            target = None
            panel.refresh_target()

            assert panel._baseline is None
            assert panel.tree.GetCount() == 0
            assert "deck on screen" in panel.target_label.GetLabel()
        finally:
            frame.Destroy()

    def test_the_same_archetype_keeps_what_is_drawn(self, wx_app):
        """Only a *change* clears; a redundant refresh must not flicker."""
        frame = wx.Frame(None)
        try:
            panel = DeckBaselinePanel(
                frame,
                worker=None,
                archetype_provider=lambda: {"name": "Boros Energy"},
                format_provider=lambda: "Modern",
            )
            panel._baseline = _baseline()
            panel._computed_for = ("Boros Energy", "Modern")
            panel.render()
            before = panel.tree.GetCount()

            panel.refresh_target()

            assert panel._baseline is not None
            assert panel.tree.GetCount() == before
        finally:
            frame.Destroy()
