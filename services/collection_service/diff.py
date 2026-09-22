"""Deck-minus-collection diff: the decklist of what is still missing (#1044).

``analyze_deck_ownership`` answers "how much of this deck do I own?" for display.
This module answers the other half: *what do I still have to get?*, and answers it
in the one format the rest of the world accepts -- a decklist. A player can paste
the result into a bot, a rental service or a trade post and buy exactly the gap.

Two things make the arithmetic less obvious than ``needed - owned`` per line:

- A collection is **one pool**. A deck that plays 4 Lightning Bolt maindeck and 2
  more in the sideboard needs 6 copies, not "4 or 2"; 3 owned copies cover the
  maindeck first and leave 1 main + 2 side missing. Requirements are therefore
  drawn against a per-name budget, mainboard before sideboard.
- Averaged decklists (:mod:`services.deck_service.averager`) carry fractional
  counts. You cannot acquire 0.4 of a card, so a zone's total is rounded up.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from services.deck_service.parser import DeckParser
from utils.card_names import fold_card_name

# Shared by every deck-text producer in the app (``build_deck_text_from_zones``)
# and understood by every consumer, including our own parser.
_SIDEBOARD_HEADER = "Sideboard"

_parser = DeckParser()


@dataclass(frozen=True)
class CollectionDiff:
    """What a deck still needs, as counts per zone plus a ready-to-save decklist."""

    mainboard: list[tuple[str, int]] = field(default_factory=list)
    sideboard: list[tuple[str, int]] = field(default_factory=list)
    text: str = ""
    missing_total: int = 0
    required_total: int = 0

    @property
    def is_empty(self) -> bool:
        """True when the collection already covers the deck."""
        return self.missing_total == 0


def _zone_totals(deck_text: str) -> tuple[list[tuple[str, float]], list[tuple[str, float]]]:
    """Split *deck_text* into ``(mainboard, sideboard)`` name/total pairs, in deck order.

    Parsing is delegated to :class:`DeckParser` rather than re-split here so the
    diff inherits its handling of the blank-line and ``Sideboard`` separators, of
    printing-id suffixes, and of junk lines.
    """
    totals: dict[bool, dict[str, float]] = {False: {}, True: {}}
    order: dict[bool, list[str]] = {False: [], True: []}

    for entry in _parser.iter_deck_entries(deck_text):
        zone = totals[entry.is_sideboard]
        if entry.name not in zone:
            order[entry.is_sideboard].append(entry.name)
        zone[entry.name] = zone.get(entry.name, 0.0) + entry.count

    return (
        [(name, totals[False][name]) for name in order[False]],
        [(name, totals[True][name]) for name in order[True]],
    )


def _draw_zone(
    zone: list[tuple[str, float]],
    budget: dict[str, int],
    owned_count: Callable[[str], int],
) -> tuple[list[tuple[str, int]], int, int]:
    """Spend *budget* on *zone*, returning ``(missing, missing_total, required_total)``.

    *budget* is mutated: it is the shared pool the next zone draws from.
    """
    missing: list[tuple[str, int]] = []
    missing_total = 0
    required_total = 0

    for name, total in zone:
        # Fractional averages round up: a shopping list cannot ask for half a card.
        required = math.ceil(total)
        if required <= 0:
            continue
        required_total += required

        # Fold so the same card reached through two spellings ("Kili" maindeck,
        # "Kili" sideboard) draws on one budget entry rather than two.
        key = fold_card_name(name) or name
        if key not in budget:
            budget[key] = max(0, owned_count(name))

        taken = min(required, budget[key])
        budget[key] -= taken

        if required > taken:
            missing.append((name, required - taken))
            missing_total += required - taken

    return missing, missing_total, required_total


def _render(mainboard: list[tuple[str, int]], sideboard: list[tuple[str, int]]) -> str:
    """Render the two zones as deck text in the app's own format."""
    if not mainboard and not sideboard:
        return ""
    lines = [f"{count} {name}" for name, count in mainboard]
    if sideboard:
        # The blank line is what ``build_deck_text_from_zones`` emits; the header
        # is there so a diff with no mainboard lines still says which zone it is.
        if lines:
            lines.append("")
        lines.append(_SIDEBOARD_HEADER)
        lines.extend(f"{count} {name}" for name, count in sideboard)
    return "\n".join(lines)


def build_collection_diff(deck_text: str, owned_count: Callable[[str], int]) -> CollectionDiff:
    """Return the cards *deck_text* needs beyond what *owned_count* reports.

    *owned_count* is the collection lookup (``CollectionService.get_owned_count``),
    injected so the diff stays a pure function over a deck string and a callable.
    """
    main_zone, side_zone = _zone_totals(deck_text)
    budget: dict[str, int] = {}

    main_missing, main_total, main_required = _draw_zone(main_zone, budget, owned_count)
    side_missing, side_total, side_required = _draw_zone(side_zone, budget, owned_count)

    return CollectionDiff(
        mainboard=main_missing,
        sideboard=side_missing,
        text=_render(main_missing, side_missing),
        missing_total=main_total + side_total,
        required_total=main_required + side_required,
    )


__all__ = ["CollectionDiff", "build_collection_diff"]
