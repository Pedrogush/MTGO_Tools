"""msgspec schemas for the atomic-cards index.

``CardEntry`` is the project-wide domain type for a single card record. It
exposes dict-compatible accessors (``get``/``__getitem__``/``__contains__``)
because widgets and tests still feed it through code paths that historically
took raw dicts.
"""

from __future__ import annotations

from typing import Any

import msgspec

#: The MTGJSON legality states that mean "you may play this card in that
#: format". MTGJSON emits exactly three values (verified against the
#: 2026-08-23 ``AtomicCards.json``: 342,773 ``Legal``, 1,217 ``Banned``,
#: 109 ``Restricted``), and ``Restricted`` is a *playable* state -- it caps the
#: deck at a single copy, it does not remove the card from the pool. Vintage is
#: the format built around that distinction: Black Lotus, Ancestral Recall,
#: Sol Ring, Brainstorm, Merchant Scroll and 48 other printings are restricted
#: there and legal nowhere else in constructed, so treating ``Restricted`` as
#: "not legal" makes a Vintage deck look like it has no format at all.
PLAYABLE_LEGALITY_STATES: frozenset[str] = frozenset({"Legal", "Restricted"})


class CardEntry(msgspec.Struct, gc=False):
    """A single card record as stored in the local atomic-cards index.

    ``gc=False`` disables cyclic-garbage-collection tracking for this type,
    which measurably reduces parse time when decoding large lists of structs.
    """

    name: str
    name_lower: str
    aliases: list[str]
    colors: list[str]
    color_identity: list[str]
    legalities: dict[str, str]
    mana_cost: str | None = None
    mana_value: float | None = None
    type_line: str | None = None
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    # Back-face fields populated for double-faced/split/MDFC/adventure cards.
    back_name: str | None = None
    back_mana_cost: str | None = None
    back_type_line: str | None = None
    back_oracle_text: str | None = None
    back_power: str | None = None
    back_toughness: str | None = None
    back_loyalty: str | None = None

    def get(self, key: str, default: Any = None) -> Any:  # noqa: ANN401
        return getattr(self, key, default)

    def __getitem__(self, key: str) -> Any:  # noqa: ANN401
        try:
            return getattr(self, key)
        except AttributeError:
            raise KeyError(key) from None

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and hasattr(self, key)


class CardIndex(msgspec.Struct):
    """Root structure of the saved atomic-cards index file.

    ``cards_by_name`` maps an alias (lowercased) to the *index* of the matching
    record in ``cards`` rather than to a duplicated ``CardEntry``. Persisting
    indices avoids serializing every card twice, which roughly halves the index
    file size and decode time; consumers rebuild a name -> ``CardEntry`` mapping
    by indexing into ``cards``.
    """

    cards: list[CardEntry]
    cards_by_name: dict[str, int]


__all__ = ["PLAYABLE_LEGALITY_STATES", "CardEntry", "CardIndex"]
