"""Priority tiers for the card-image download queue (issue #951).

Lower value = downloaded sooner. The queue is FIFO within a tier, so a batch
submitted in display order resolves in display order. The tiers encode how
likely the user is to look at the image next:

- ``PRIORITY_HOVER`` — the card under the cursor / shown in the inspector.
- ``PRIORITY_SELECTED_DECK`` — every card of the deck currently open in the
  UI; the whole deck is visible-or-one-hover-away the moment it loads.
- ``PRIORITY_RESEARCH_VISIBLE`` — the top decks of the research results list
  for the *selected* format and the visible window of the card search.
- ``PRIORITY_RESEARCH_FORMATS`` — the decks the research panel would show
  for the other formats (warmed alphabetically by format).
- ``PRIORITY_FORMAT_ALL`` — every remaining deck of the selected format.
- ``PRIORITY_BACKGROUND`` — every deck of every other format; the exhaustive
  "each competitively played card eventually" sweep.
"""

PRIORITY_HOVER = 0
PRIORITY_SELECTED_DECK = 1
PRIORITY_RESEARCH_VISIBLE = 2
PRIORITY_RESEARCH_FORMATS = 3
PRIORITY_FORMAT_ALL = 4
PRIORITY_BACKGROUND = 5

PRIORITY_TIERS = (
    PRIORITY_HOVER,
    PRIORITY_SELECTED_DECK,
    PRIORITY_RESEARCH_VISIBLE,
    PRIORITY_RESEARCH_FORMATS,
    PRIORITY_FORMAT_ALL,
    PRIORITY_BACKGROUND,
)

# Batches at or above this urgency (numerically <=) are user-driven: they run
# immediately, bypassing the prefetcher's startup grace delay.
PRIORITY_USER_DRIVEN_MAX = PRIORITY_RESEARCH_VISIBLE

__all__ = [
    "PRIORITY_BACKGROUND",
    "PRIORITY_FORMAT_ALL",
    "PRIORITY_HOVER",
    "PRIORITY_RESEARCH_FORMATS",
    "PRIORITY_RESEARCH_VISIBLE",
    "PRIORITY_SELECTED_DECK",
    "PRIORITY_TIERS",
    "PRIORITY_USER_DRIVEN_MAX",
]
