"""The per-card frequency table the whole baseline is derived from.

This is deliberately *not* pairwise diffing across the pool. Comparing every
deck against every other is O(N^2) and answers a different question -- "how far
apart are these two lists" -- when what a baseline needs is "how often does the
archetype run this card, and how many". One pass per deck, counting cards,
answers that in O(total card lines) and is the only pass over the pool anyone
downstream needs.

Zones are kept apart throughout: four copies of a card in the sideboard is a
different fact from four in the main deck, and collapsing them would invent
staples that no list actually runs.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from repositories.deck_vcs_repository.normalize import parse_entries
from services.archetype_baseline_service.models import CardFrequency

#: A card is keyed by name *and* zone, so the two zones never merge.
CardKey = tuple[str, bool]


def deck_card_counts(deck_text: str) -> dict[CardKey, float]:
    """One deck's cards as ``(name, is_sideboard) -> count``.

    Uses the deck-VCS canonical parser rather than a second one, so a decklist
    counts the same here as it would if it were committed: duplicate lines are
    summed, junk lines ignored, zone split identical.
    """
    counts: dict[CardKey, float] = {}
    for entry in parse_entries(deck_text):
        key = (entry.name, entry.is_sideboard)
        counts[key] = counts.get(key, 0.0) + entry.count
    return counts


def zone_size(counts: dict[CardKey, float], *, is_sideboard: bool) -> float:
    return sum(count for (_name, side), count in counts.items() if side is is_sideboard)


def build_frequency_table(deck_texts: Sequence[str]) -> dict[CardKey, CardFrequency]:
    """Measure every card across the pool.

    The returned table holds, per card, how many decks run it and the
    distribution of counts *among those decks* -- the two numbers every
    classification below depends on.
    """
    pool = [deck_card_counts(text) for text in deck_texts if text and text.strip()]
    pool_size = len(pool)
    if not pool_size:
        return {}

    decks_with: dict[CardKey, int] = {}
    distributions: dict[CardKey, dict[float, int]] = {}

    for deck in pool:
        for key, count in deck.items():
            if count <= 0:
                continue
            decks_with[key] = decks_with.get(key, 0) + 1
            bucket = distributions.setdefault(key, {})
            bucket[count] = bucket.get(count, 0) + 1

    return {
        key: CardFrequency(
            name=key[0],
            is_sideboard=key[1],
            decks_with=decks_with[key],
            pool_size=pool_size,
            counts=dict(distributions[key]),
        )
        for key in decks_with
    }


def median(values: Iterable[float]) -> float:
    """Median of ``values``, 0.0 when empty.

    The pool's zone sizes are summarized with a median rather than a mean
    because one 80-card Yorion list (or one truncated scrape) should not drag
    the baseline's notion of "how big is this deck" off the value almost every
    deck in the pool actually has.
    """
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def pool_zone_sizes(deck_texts: Sequence[str]) -> tuple[float, float]:
    """The pool's typical ``(main, sideboard)`` size.

    Derived from the pool rather than hardcoded to 60/15: Yorion lists are 80,
    and a format whose decks are a different size would otherwise get a flex
    slot count that is wrong by a constant.
    """
    pool = [deck_card_counts(text) for text in deck_texts if text and text.strip()]
    if not pool:
        return (0.0, 0.0)
    main = median(zone_size(deck, is_sideboard=False) for deck in pool)
    side = median(zone_size(deck, is_sideboard=True) for deck in pool)
    return (main, side)
