"""Grouping a deck's lands by what they produce, and enumerating combinations.

Two basic ``Forest``s are the same land for this question, and so are a
``Steam Vents`` and a ``Sulfur Falls`` -- both tap for one unit of ``{U, R}``,
and which one it is never changes what the deck can cast. So lands are grouped
by :class:`~services.deck_patterns_service.mana.LandProduction` and the
combinations enumerated are count vectors over those groups (a multinomial),
not combinations over individual land objects. A 24-land deck of four distinct
profiles gives tens of combinations at turn 6 rather than the hundreds of
thousands ``C(24, 6)`` would.

The colour choice inside a dual stays *unresolved* here. A group records that
it taps for one unit of ``{U, R}``; which of the two it actually makes is
decided during castability checking, against the specific play being tested.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from services.deck_patterns_service.castability import ManaUnit
from services.deck_patterns_service.mana import LandProduction


@dataclass(frozen=True)
class LandGroup:
    """One production profile, the land names that share it, and how many exist."""

    production: LandProduction
    names: tuple[str, ...]
    count: int

    @property
    def label(self) -> str:
        """What to show for this group -- the name when it is the only one."""
        if len(self.names) == 1:
            return self.names[0]
        return " / ".join(self.names)


@dataclass(frozen=True)
class LandCombination:
    """How many of each land group are in play, and the mana that yields."""

    #: Parallel to the group list it was enumerated from.
    counts: tuple[int, ...]
    groups: tuple[LandGroup, ...]

    @property
    def units(self) -> tuple[ManaUnit, ...]:
        """The individual mana units these lands make, one entry per unit."""
        units: list[ManaUnit] = []
        for count, group in zip(self.counts, self.groups, strict=True):
            if not count:
                continue
            units.extend([group.production.options] * (count * group.production.amount))
        return tuple(units)

    @property
    def profile(self) -> tuple[ManaUnit, ...]:
        """The cache key: the same units, in a canonical order.

        Different land combinations collapse onto one profile -- a ``Forest``
        plus an ``Island`` and an ``Island`` plus a ``Forest`` are one key --
        which is what makes caching the play search by profile pay off.
        """
        return tuple(sorted(self.units, key=lambda unit: tuple(sorted(unit))))

    @property
    def total_mana(self) -> int:
        return len(self.units)

    def entries(self) -> tuple[tuple[LandGroup, int], ...]:
        """The groups actually present, with their counts."""
        return tuple(
            (group, count) for count, group in zip(self.counts, self.groups, strict=True) if count
        )


def group_lands(lands: dict[str, tuple[int, LandProduction]]) -> tuple[LandGroup, ...]:
    """Collapse ``{name: (qty, production)}`` into groups sharing a production.

    Lands that tap for nothing readable are dropped: they cannot contribute to
    a mana total, and keeping them would inflate every combination with a land
    that pays for nothing.
    """
    by_production: dict[LandProduction, list[tuple[str, int]]] = {}
    for name, (qty, production) in lands.items():
        if not production.produces_mana or qty <= 0:
            continue
        by_production.setdefault(production, []).append((name, qty))

    groups: list[LandGroup] = []
    for production, members in by_production.items():
        names = tuple(sorted(name for name, _ in members))
        groups.append(
            LandGroup(
                production=production,
                names=names,
                count=sum(qty for _, qty in members),
            )
        )
    # Deterministic order, so combinations and their screenshots are stable.
    groups.sort(key=lambda g: (-g.production.amount, sorted(g.production.options), g.names))
    return tuple(groups)


def enumerate_combinations(
    groups: tuple[LandGroup, ...], land_count: int
) -> Iterator[LandCombination]:
    """Every way to pick ``land_count`` lands from ``groups``.

    Yields count vectors summing to ``land_count``, each bounded by how many of
    that group the deck actually runs.
    """
    if land_count <= 0 or not groups:
        return

    counts: list[int] = [0] * len(groups)

    def walk(index: int, remaining: int) -> Iterator[LandCombination]:
        if remaining == 0:
            yield LandCombination(counts=tuple(counts), groups=groups)
            return
        if index >= len(groups):
            return
        # Prune: even taking every remaining group in full cannot reach the target.
        if sum(g.count for g in groups[index:]) < remaining:
            return
        take_max = min(groups[index].count, remaining)
        for take in range(take_max, -1, -1):
            counts[index] = take
            yield from walk(index + 1, remaining - take)
        counts[index] = 0

    yield from walk(0, land_count)


__all__ = [
    "LandCombination",
    "LandGroup",
    "enumerate_combinations",
    "group_lands",
]
