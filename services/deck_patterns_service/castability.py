"""Deciding whether a set of mana units can pay a set of costs.

**This is exact, not approximate.** §2.3 of the feature spec offers a choice
between precise bipartite matching and an approximation over totals plus
per-colour counts, and the approximation is wrong in the most ordinary case a
modern deck presents. Two ``Steam Vents`` (each ``{U}`` *or* ``{R}``) satisfy a
per-colour count check for ``{U}{U}`` and for ``{R}{R}`` simultaneously, because
counting says "2 sources of U, 2 sources of R"; in fact each land picks one
colour, so a deck holding exactly those two lands can pay ``{U}{R}`` but not
``{U}{U}{R}``. Every dual, triome and fetch in a real mana base has that shape,
so the cheap check would over-report on most decks in the format.

The exact version costs almost nothing here: a turn caps the board at ~7 mana
units and a play at ~7 coloured pips, so Kuhn's augmenting-path algorithm runs
on a graph of a few dozen edges. It is run once per distinct mana profile
(:mod:`services.deck_patterns_service.search`), not once per land combination.

What remains simplified is stated where it is introduced, not here: mana units
choose colours independently (:mod:`services.deck_patterns_service.mana`), and
costs are the printed ones -- no cost reduction, alternative costs, or ``X``
above zero.
"""

from __future__ import annotations

from services.deck_patterns_service.mana import ManaCost

#: One mana unit's colour options, e.g. ``frozenset({"U", "R"})``.
ManaUnit = frozenset[str]


def _augment(
    pip_index: int,
    adjacency: list[list[int]],
    matched_unit_for_pip: list[int],
    matched_pip_for_unit: list[int],
    seen: list[bool],
) -> bool:
    """Try to find an augmenting path for ``pip_index`` (Kuhn's algorithm)."""
    for unit in adjacency[pip_index]:
        if seen[unit]:
            continue
        seen[unit] = True
        holder = matched_pip_for_unit[unit]
        if holder == -1 or _augment(
            holder, adjacency, matched_unit_for_pip, matched_pip_for_unit, seen
        ):
            matched_pip_for_unit[unit] = pip_index
            matched_unit_for_pip[pip_index] = unit
            return True
    return False


def can_pay(units: tuple[ManaUnit, ...], costs: tuple[ManaCost, ...]) -> bool:
    """Whether ``units`` can pay every cost in ``costs`` at once.

    Coloured pips are matched to distinct units exactly; whatever units the
    matching leaves over pay the combined generic amount.
    """
    pips: list[ManaUnit] = []
    generic = 0
    for cost in costs:
        generic += cost.generic
        pips.extend(cost.pips)

    if generic + len(pips) > len(units):
        return False
    if not pips:
        return True

    # A pip with no payable colour (an unreadable hybrid) can never be paid.
    adjacency: list[list[int]] = []
    for pip in pips:
        payable = [i for i, unit in enumerate(units) if unit & pip]
        if not payable:
            return False
        adjacency.append(payable)

    # Match the most constrained pips first: fewer augmenting passes.
    order = sorted(range(len(pips)), key=lambda i: len(adjacency[i]))

    matched_unit_for_pip = [-1] * len(pips)
    matched_pip_for_unit = [-1] * len(units)
    matched = 0
    for pip_index in order:
        seen = [False] * len(units)
        if _augment(pip_index, adjacency, matched_unit_for_pip, matched_pip_for_unit, seen):
            matched += 1

    if matched < len(pips):
        return False
    return len(units) - len(pips) >= generic


__all__ = ["ManaUnit", "can_pay"]
