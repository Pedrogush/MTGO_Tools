"""Reading mana costs and land mana production out of card data.

Two directions, both driven by the atomic-cards index this app already ships:

*Spending* -- :func:`parse_mana_cost` turns a cost string like ``{2}{R}{R}``
into a generic amount plus a list of coloured pips, where each pip carries the
*set* of colours that can pay it (so hybrid is one pip with two options rather
than two costs to try).

*Producing* -- :func:`parse_land_production` reads what a land taps for. The
index has no ``produced_mana`` field (see
:class:`repositories.card_repository.schemas.CardEntry`), so production is
derived from the oracle text's ``Add ...`` clause, with the type line's basic
land types as the fallback for a card whose reminder text is missing.

A land is modelled as *amount* mana units that each independently choose a
colour from one option set: ``Ancient Tomb`` is two units of ``{C}``, and
``Steam Vents`` is one unit of ``{U, R}``. That independence is the one real
simplification here and it is what makes a land's production hashable, which is
what lets the play search be cached per mana profile. It mis-models a land that
adds two mana which must be *the same* colour, or two of *different* colours;
both are rare enough to be worth the exactness everywhere else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: The five colours plus colourless, in WUBRG order.
COLORS: tuple[str, ...] = ("W", "U", "B", "R", "G")
COLORLESS = "C"
ALL_COLORS = frozenset(COLORS)

#: ``{T}: Add {G}.`` / ``Add {U} or {R}.`` / ``Add {U}, {R}, or {W}.``
_ADD_CLAUSE = re.compile(r"\badd\b([^.;]*)", re.IGNORECASE)
_SYMBOL = re.compile(r"\{([^}]+)\}")
_ANY_COLOR = re.compile(r"one mana of any colou?r", re.IGNORECASE)
_ANY_TYPE = re.compile(r"one mana of any type", re.IGNORECASE)

#: Basic land type -> the colour it taps for, used when reminder text is absent.
_BASIC_TYPE_COLORS = {
    "plains": "W",
    "island": "U",
    "swamp": "B",
    "mountain": "R",
    "forest": "G",
    "wastes": COLORLESS,
}


@dataclass(frozen=True)
class ManaCost:
    """A spell's cost, split into what colour constrains and what does not.

    ``pips`` holds one entry per coloured symbol; each entry is the set of
    colours able to pay that symbol, so ``{U/R}`` is ``frozenset({"U", "R"})``
    and a plain ``{R}`` is ``frozenset({"R"})``.
    """

    generic: int = 0
    pips: tuple[frozenset[str], ...] = ()
    has_x: bool = False

    @property
    def total(self) -> int:
        """Total mana units needed, with ``X`` taken as zero."""
        return self.generic + len(self.pips)


@dataclass(frozen=True)
class LandProduction:
    """What one land taps for: ``amount`` units, each choosing from ``options``."""

    amount: int = 0
    options: frozenset[str] = frozenset()

    @property
    def produces_mana(self) -> bool:
        return self.amount > 0 and bool(self.options)


#: A land that taps for nothing we could read.
NO_PRODUCTION = LandProduction()


def parse_mana_cost(cost: str | None) -> ManaCost:
    """Parse ``{2}{R}{R}`` into generic 2 and two ``{R}`` pips.

    Symbol handling, and the three places v1 rounds off:

    * ``{X}`` sets :attr:`ManaCost.has_x` and contributes nothing, i.e. the
      capability ceiling is computed for ``X = 0``.
    * ``{2/R}`` (monocoloured hybrid) is counted as 2 generic. Taking it as an
      ``{R}`` pip instead would understate what a colourless mana base can do,
      and this direction never reports a play the deck cannot actually make.
    * ``{U/P}`` (Phyrexian) is counted as a ``{U}`` pip rather than as free.
      Paying 2 life is always available, so this *understates* the ceiling, but
      the alternative reports plays that cost life without saying so.
    """
    if not cost:
        return ManaCost()

    generic = 0
    pips: list[frozenset[str]] = []
    has_x = False

    for raw in _SYMBOL.findall(cost):
        symbol = raw.strip().upper()
        if not symbol:
            continue
        if symbol in {"X", "Y", "Z"}:
            has_x = True
            continue
        if symbol.isdigit():
            generic += int(symbol)
            continue
        if symbol == "S":  # snow mana is payable by any source here
            generic += 1
            continue
        if symbol == COLORLESS:
            pips.append(frozenset({COLORLESS}))
            continue

        parts = [p.strip() for p in symbol.split("/") if p.strip()]
        if not parts:
            continue
        if len(parts) == 1:
            if parts[0] in ALL_COLORS:
                pips.append(frozenset({parts[0]}))
            else:
                generic += 1
            continue

        # Hybrid. Phyrexian keeps the colour; a numeric half becomes generic.
        if "P" in parts:
            colors = {p for p in parts if p in ALL_COLORS}
            pips.append(frozenset(colors) if colors else frozenset())
            continue
        numeric = [p for p in parts if p.isdigit()]
        if numeric:
            generic += max(int(n) for n in numeric)
            continue
        colors = {p for p in parts if p in ALL_COLORS}
        if colors:
            pips.append(frozenset(colors))
        else:
            generic += 1

    return ManaCost(generic=generic, pips=tuple(pips), has_x=has_x)


def _options_from_clause(clause: str) -> tuple[int, frozenset[str]]:
    """Read one ``Add ...`` clause into (units, colour options)."""
    if _ANY_COLOR.search(clause):
        return 1, ALL_COLORS
    if _ANY_TYPE.search(clause):
        return 1, ALL_COLORS | {COLORLESS}

    symbols = [s.strip().upper() for s in _SYMBOL.findall(clause)]
    produced = [s for s in symbols if s in ALL_COLORS or s == COLORLESS]
    if not produced:
        return 0, frozenset()

    distinct = set(produced)
    # "Add {U} or {R}" and "Add {U}, {R}, or {W}" list alternatives for a single
    # unit; "Add {C}{C}" repeats the same symbol, which is two units.
    if len(distinct) == 1:
        return len(produced), frozenset(distinct)
    if " or " in clause.lower() or "," in clause:
        return 1, frozenset(distinct)
    return len(produced), frozenset(distinct)


def parse_land_production(oracle_text: str | None, type_line: str | None = None) -> LandProduction:
    """What a land taps for, from its reminder/oracle text or its basic types.

    Several ``Add`` clauses on one card are alternatives for a single tap, so
    their colour options are unioned and the unit count is the largest any one
    clause offers.
    """
    amount = 0
    options: set[str] = set()

    for clause in _ADD_CLAUSE.findall(oracle_text or ""):
        clause_amount, clause_options = _options_from_clause(clause)
        if clause_amount:
            amount = max(amount, clause_amount)
            options |= clause_options

    if amount and options:
        return LandProduction(amount=amount, options=frozenset(options))

    # No readable Add clause: fall back to the basic land types on the type line
    # ("Land — Island Mountain" taps for U or R even with the reminder stripped).
    lowered = (type_line or "").lower()
    from_types = {color for name, color in _BASIC_TYPE_COLORS.items() if name in lowered}
    if from_types:
        return LandProduction(amount=1, options=frozenset(from_types))

    return NO_PRODUCTION


__all__ = [
    "ALL_COLORS",
    "COLORLESS",
    "COLORS",
    "NO_PRODUCTION",
    "LandProduction",
    "ManaCost",
    "parse_land_production",
    "parse_mana_cost",
]
