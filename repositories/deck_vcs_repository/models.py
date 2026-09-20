"""Plain records the deck-VCS layers hand upward.

The UI and the service layer never see a dulwich object: everything crosses the
boundary as one of these, so the graph panel can be built and tested without a
repo on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DeckCommit:
    """One saved version of a deck."""

    sha: str
    parents: tuple[str, ...]
    message: str
    timestamp: int
    #: Names of branches whose tip is this commit (empty for interior commits).
    branches: tuple[str, ...] = ()
    #: True for the commit ``HEAD`` currently resolves to.
    is_head: bool = False

    @property
    def short_sha(self) -> str:
        return self.sha[:7]


@dataclass(frozen=True)
class CardDelta:
    """One card's change between two versions."""

    name: str
    before: float
    after: float
    is_sideboard: bool

    @property
    def delta(self) -> float:
        return self.after - self.before


@dataclass(frozen=True)
class DeckDiff:
    """The card-level difference between two decklists."""

    added: tuple[CardDelta, ...] = field(default_factory=tuple)
    removed: tuple[CardDelta, ...] = field(default_factory=tuple)
    changed: tuple[CardDelta, ...] = field(default_factory=tuple)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def summary(self, *, limit: int = 4) -> str:
        """A one-line ``+2 Fable, -2 Consider`` style summary, for a graph node.

        ``limit`` caps how many cards are named before the rest is counted, so a
        node label stays a label rather than becoming a decklist.
        """
        parts: list[str] = []
        for delta in (*self.added, *self.changed, *self.removed):
            sign = "+" if delta.delta > 0 else ""
            amount = delta.delta
            rendered = int(amount) if float(amount).is_integer() else amount
            parts.append(f"{sign}{rendered} {delta.name}")
        if not parts:
            return ""
        if len(parts) <= limit:
            return ", ".join(parts)
        return ", ".join(parts[:limit]) + f", +{len(parts) - limit} more"
