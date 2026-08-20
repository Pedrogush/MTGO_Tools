"""§4.6 — the inspector column is one card, not two.

Until phase 7 the right column stacked ``Card Inspector`` (image + printing
pager) over ``Card`` (Oracle Text / Stats). Two headings for one object, neither
naming what distinguished it from the other. Phase 6 (#971) also measured the
cost: the both-panels-expanded minimum height rose 902 → 918 when two real
headings replaced two ``wx.StaticBox`` grooves, and recorded that phase 7's merge
would get it back.

The obvious regression is someone re-adding a section for the tabs, so that is
what these pin.
"""

from __future__ import annotations

import pytest
import wx

from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_panel import CardPanel
from widgets.section import SectionPanel


def _sections(window: wx.Window) -> list[SectionPanel]:
    found: list[SectionPanel] = []

    def walk(win: wx.Window) -> None:
        for child in win.GetChildren():
            if isinstance(child, SectionPanel):
                found.append(child)
            walk(child)

    walk(window)
    return found


@pytest.mark.usefixtures("wx_app")
def test_the_inspector_column_holds_exactly_one_section_card(deck_selector_factory) -> None:
    frame = deck_selector_factory()
    try:
        sections = _sections(frame.inspector_panel)
        assert len(sections) == 1, [s.heading.GetLabel() if s.heading else None for s in sections]
        assert sections[0].heading is not None
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_both_inspector_halves_live_inside_that_one_section(deck_selector_factory) -> None:
    """The merge must not have dropped either half — the art or the tabs."""
    frame = deck_selector_factory()
    try:
        section = _sections(frame.inspector_panel)[0]

        def ancestors(win: wx.Window) -> list[wx.Window]:
            chain = []
            node = win.GetParent()
            while node is not None:
                chain.append(node)
                node = node.GetParent()
            return chain

        assert isinstance(frame.card_inspector_panel, CardInspectorPanel)
        assert isinstance(frame.card_panel, CardPanel)
        assert section.body in ancestors(frame.card_inspector_panel)
        assert section.body in ancestors(frame.card_panel)
    finally:
        frame.Destroy()
