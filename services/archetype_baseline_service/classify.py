"""Turning the frequency table into staples, partial staples and flex.

The three-way split is the point of the whole feature. A modal decklist -- the
most common list in the pool -- answers "what did one player register", which is
not what a deck builder needs. The useful answer separates the slots the
archetype has already decided (staples, and the floor of every partial staple)
from the slots it has not (everything else), because the second set is where the
player's own choices actually live.

The staple threshold is a parameter rather than a constant because pool size
changes what "everyone runs it" can mean: in a pool of six decks a strict 100%
cut-off turns a single rogue list into a veto over every card it dropped.
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

#: Default cut-off for "in (almost) every deck". Not 1.0: one incomplete scrape
#: or one genuinely rogue list in an otherwise uniform pool should not be able
#: to demote a card the archetype obviously always runs.
DEFAULT_STAPLE_THRESHOLD = 0.9


def classify_card(frequency: CardFrequency, *, threshold: float) -> tuple[CardRole, float]:
    """``(role, fixed_count)`` for one measured card.

    A card at or above the threshold is fixed at the count every deck shares, or
    -- when the count moves -- at its floor, with the remainder left to flex.
    Below the threshold nothing is fixed at all.
    """
    if frequency.play_rate >= threshold and frequency.decks_with > 0:
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
    threshold: float = DEFAULT_STAPLE_THRESHOLD,
    sources: tuple[str, ...] = (),
) -> ArchetypeBaseline:
    """Compute the baseline of the pool in ``deck_texts``."""
    from services.archetype_baseline_service.frequency import pool_zone_sizes

    table: dict[CardKey, CardFrequency] = build_frequency_table(deck_texts)
    pool_size = next(iter(table.values())).pool_size if table else 0

    cards: list[BaselineCard] = []
    for frequency in table.values():
        role, fixed = classify_card(frequency, threshold=threshold)
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
        threshold=threshold,
        cards=ordered,
        flex_candidates=build_flex_candidates(ordered),
        main=ZoneShape(size=main_size, fixed=main_fixed),
        sideboard=ZoneShape(size=side_size, fixed=side_fixed),
        sources=sources,
    )
