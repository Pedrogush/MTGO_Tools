"""The records the baseline analysis produces.

Everything here is a plain frozen dataclass so the whole computation can be
tested without a repo, a cache or a wx window, and so a baseline can be written
to JSON and read back as the same thing it was when it was computed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class CardRole(Enum):
    """What a card is, relative to the pool it was measured in."""

    #: In (almost) every deck, always at the same count. Fully fixed.
    STAPLE = "staple"
    #: In (almost) every deck, but the count moves. The floor is fixed; the rest
    #: is flex, which is the distinction a modal decklist throws away.
    PARTIAL_STAPLE = "partial_staple"
    #: In a meaningfully smaller share of the pool. Entirely flex.
    FLEX = "flex"


@dataclass(frozen=True)
class CardFrequency:
    """One card's measurements across the pool, before any classification.

    ``counts`` is the distribution *among decks that run the card* -- count to
    number of decks -- which is what separates "everyone runs exactly 4" from
    "everyone runs between 1 and 4".
    """

    name: str
    is_sideboard: bool
    decks_with: int
    pool_size: int
    counts: dict[float, int] = field(default_factory=dict)

    @property
    def play_rate(self) -> float:
        """Fraction of the pool running this card at all."""
        if self.pool_size <= 0:
            return 0.0
        return self.decks_with / self.pool_size

    @property
    def floor_count(self) -> float:
        """The lowest count among decks that run it -- the fixed part."""
        return min(self.counts) if self.counts else 0.0

    @property
    def max_count(self) -> float:
        return max(self.counts) if self.counts else 0.0

    @property
    def is_uniform(self) -> bool:
        """True when every deck that runs it runs the same number."""
        return len(self.counts) == 1

    @property
    def average_count(self) -> float:
        """Mean count among decks that run it (not across the whole pool)."""
        if not self.decks_with:
            return 0.0
        total = sum(count * decks for count, decks in self.counts.items())
        return total / self.decks_with


@dataclass(frozen=True)
class BaselineCard:
    """One card after classification, with the slot count the baseline fixes."""

    name: str
    is_sideboard: bool
    role: CardRole
    #: What the baseline decklist runs: the staple count, or a partial staple's
    #: floor. Zero for flex cards, which the baseline does not commit to.
    fixed_count: float
    frequency: CardFrequency

    @property
    def play_rate(self) -> float:
        return self.frequency.play_rate

    @property
    def flex_above_floor(self) -> float:
        """Slots this card *sometimes* takes beyond the ones it always takes."""
        return self.frequency.max_count - self.fixed_count


@dataclass(frozen=True)
class FlexCandidate:
    """A card competing for the flex slots, and how often it wins one."""

    name: str
    is_sideboard: bool
    play_rate: float
    average_count: float
    #: True when this is the variable part of a card the baseline already fixes
    #: at a floor, rather than a card the baseline leaves out entirely.
    above_floor: bool


@dataclass(frozen=True)
class ZoneShape:
    """How many slots a zone has, and how many the baseline has spent."""

    size: float
    fixed: float

    @property
    def flex(self) -> float:
        """Slots the baseline does not commit to. Never negative."""
        return max(0.0, self.size - self.fixed)


@dataclass(frozen=True)
class ArchetypeBaseline:
    """The computed baseline of one archetype in one format."""

    archetype: str
    mtg_format: str
    pool_size: int
    cards: tuple[BaselineCard, ...]
    flex_candidates: tuple[FlexCandidate, ...]
    main: ZoneShape
    sideboard: ZoneShape
    #: Deck numbers the pool was drawn from, so a baseline can say what it saw.
    sources: tuple[str, ...] = ()

    def by_role(self, role: CardRole, *, is_sideboard: bool | None = None) -> list[BaselineCard]:
        return [
            card
            for card in self.cards
            if card.role is role and (is_sideboard is None or card.is_sideboard == is_sideboard)
        ]

    @property
    def staples(self) -> list[BaselineCard]:
        return self.by_role(CardRole.STAPLE)

    @property
    def partial_staples(self) -> list[BaselineCard]:
        return self.by_role(CardRole.PARTIAL_STAPLE)

    @property
    def flex(self) -> list[BaselineCard]:
        return self.by_role(CardRole.FLEX)

    @property
    def flex_slots(self) -> float:
        """Uncommitted slots across both zones."""
        return self.main.flex + self.sideboard.flex

    def decklist(self) -> str:
        """The baseline as an ordinary decklist.

        Staples at their count and partial staples at their floor -- nothing
        else. It is deliberately an *incomplete* decklist: the missing cards are
        the flex slots, and inventing picks for them would be presenting one
        arbitrary list as the archetype.
        """
        from repositories.deck_vcs_repository.normalize import normalize_decklist

        lines: list[str] = []
        for card in self.cards:
            if card.fixed_count <= 0:
                continue
            count = card.fixed_count
            rendered = int(count) if float(count).is_integer() else count
            lines.append(f"{rendered} {card.name}")
            if card.is_sideboard:
                lines[-1] = f"SIDEBOARD::{lines[-1]}"

        main_lines = [line for line in lines if not line.startswith("SIDEBOARD::")]
        side_lines = [
            line[len("SIDEBOARD::") :] for line in lines if line.startswith("SIDEBOARD::")
        ]

        text = "\n".join(main_lines)
        if side_lines:
            text += "\n\nSideboard\n" + "\n".join(side_lines)
        # Normalized here so the baseline text is byte-identical to what the
        # deck repo would store for it -- the root commit and any later save of
        # the same cards then produce the same blob.
        return normalize_decklist(text)
