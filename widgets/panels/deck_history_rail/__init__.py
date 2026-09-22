"""The version rail: the deck's history beside the cards, not a tab away.

The History tab is where a version is *studied* -- its decklist, its diff, its
branches. The rail is where one is *reached*: a narrow column of the same nodes
standing next to the mainboard, so moving between versions does not cost a trip
out of the deck tables and back.

The two share their placement (:mod:`widgets.panels.deck_history_panel.layout`)
and their reading: the frame reads a deck's history once and hands the same
snapshot to both, so the rail costs no extra trip into the repo.

**A click here is a checkout.** That is the difference from the tab, where a
click previews and checking out is a separate action -- there is no preview pane
in a strip this wide, so the click has to mean the thing the strip is for.
"""

from widgets.panels.deck_history_rail.rail import DeckHistoryRail

__all__ = ["DeckHistoryRail"]
