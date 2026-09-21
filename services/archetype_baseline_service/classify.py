"""Turning the frequency table into a baseline and the flex slots around it.

The baseline is the **strict intersection** of the pool, taken at each card's
floor count: count every card in every deck, and if the minimum across the whole
pool is at least one, the card is in the baseline at that minimum. A card that
even one deck leaves out is not in the baseline at all -- its range is 0-to-N,
and there is no defensible count to fix it at.

There is deliberately **no threshold**. A cut-off would be an arbitrary choice
about how much disagreement still counts as consensus, and the whole value of
the answer is that it contains no such choice: every card here is one that every
single list in the pool committed to, at a count every single list can afford.

The consequence is that a baseline is normally **smaller than 60 main / 15
side**, and that is the correct result rather than a shortfall to pad out. What
is left over is reported as flex slots, with the cards that just missed ranked
beside them -- that, not a modal decklist, is where the player's own choices
live.
"""

from __future__ import annotations

from services.archetype_baseline_service.frequency import CardKey, build_frequency_table
from services.archetype_baseline_service.models import (
    ArchetypeBaseline,
    BaselineCard,
    CardFrequency,
    CardRole,
    FlexCandidate,
    ZoneShape,
)


def classify_card(frequency: CardFrequency) -> tuple[CardRole, float]:
    """``(role, fixed_count)`` for one measured card.

    In every deck in the pool -> fixed at the floor count, which is what every
    deck can afford. Missing from even one deck -> nothing is fixed, because the
    card's range starts at zero.

    The staple / partial-staple split that remains is purely descriptive -- same
    count everywhere, or a count that moves above a shared floor -- and no longer
    decides whether a card is in the baseline.
    """
    in_every_deck = frequency.pool_size > 0 and frequency.decks_with == frequency.pool_size
    if in_every_deck and frequency.floor_count >= 1:
        if frequency.is_uniform:
            return (CardRole.STAPLE, frequency.floor_count)
        return (CardRole.PARTIAL_STAPLE, frequency.floor_count)
    return (CardRole.FLEX, 0.0)


def _sort_key(card: BaselineCard) -> tuple[bool, float, str]:
    # Main deck before sideboard, then most-played first, then by name so the
    # order is total and a baseline renders the same way twice.
    return (card.is_sideboard, -card.play_rate, card.name.casefold())


def build_flex_candidates(cards: tuple[BaselineCard, ...]) -> tuple[FlexCandidate, ...]:
    """The ranked list of cards competing for the uncommitted slots.

    Two different things compete for them, and both belong here: cards the
    baseline leaves out entirely, and the part of a partial staple that sits
    above its floor. Reporting only the first would hide that "3-or-4 Consider"
    is itself one of the choices being made.
    """
    candidates: list[FlexCandidate] = []
    for card in cards:
        if card.role is CardRole.FLEX:
            candidates.append(
                FlexCandidate(
                    name=card.name,
                    is_sideboard=card.is_sideboard,
                    play_rate=card.play_rate,
                    average_count=card.frequency.average_count,
                    above_floor=False,
                )
            )
        elif card.role is CardRole.PARTIAL_STAPLE and card.flex_above_floor > 0:
            candidates.append(
                FlexCandidate(
                    name=card.name,
                    is_sideboard=card.is_sideboard,
                    play_rate=card.play_rate,
                    average_count=card.frequency.average_count,
                    above_floor=True,
                )
            )
    # Ranked by how often the pool plays the card, which is the question a
    # builder filling a flex slot is actually asking.
    candidates.sort(
        key=lambda c: (c.is_sideboard, -c.play_rate, -c.average_count, c.name.casefold())
    )
    return tuple(candidates)


def build_baseline(
    deck_texts: list[str],
    *,
    archetype: str,
    mtg_format: str,
    sources: tuple[str, ...] = (),
) -> ArchetypeBaseline:
    """Compute the baseline of the pool in ``deck_texts``."""
    from services.archetype_baseline_service.frequency import pool_zone_sizes

    table: dict[CardKey, CardFrequency] = build_frequency_table(deck_texts)
    pool_size = next(iter(table.values())).pool_size if table else 0

    cards: list[BaselineCard] = []
    for frequency in table.values():
        role, fixed = classify_card(frequency)
        cards.append(
            BaselineCard(
                name=frequency.name,
                is_sideboard=frequency.is_sideboard,
                role=role,
                fixed_count=fixed,
                frequency=frequency,
            )
        )
    cards.sort(key=_sort_key)
    ordered = tuple(cards)

    main_size, side_size = pool_zone_sizes(deck_texts)
    main_fixed = sum(c.fixed_count for c in ordered if not c.is_sideboard)
    side_fixed = sum(c.fixed_count for c in ordered if c.is_sideboard)

    return ArchetypeBaseline(
        archetype=archetype,
        mtg_format=mtg_format,
        pool_size=pool_size,
        cards=ordered,
        flex_candidates=build_flex_candidates(ordered),
        main=ZoneShape(size=main_size, fixed=main_fixed),
        sideboard=ZoneShape(size=side_size, fixed=side_fixed),
        sources=sources,
    )
