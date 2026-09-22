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
