"""Finding the maximal plays a given pile of mana can make.

"Maximal" rather than "every": for ``k`` affordable cards the power set is up to
``2**k`` subsets, and almost all of them are dominated -- if a deck can cast
``Lightning Bolt`` *and* ``Consider`` off two mana, reporting "Bolt alone" and
"Consider alone" beside "both" tells the reader nothing they cannot see. A play
is kept only when no further copy of any card can be added to it and still be
castable.

The search is keyed by **mana profile**, not by land combination
(:class:`~services.deck_patterns_service.lands.LandCombination`), because many
combinations produce the same units and so have the same answer. The spec calls
this the single biggest performance win available, and it is: a typical two
colour deck collapses dozens of turn-6 combinations onto a handful of profiles.

Pathological decks are bounded by a node budget rather than by trusting the
pruning. When the budget runs out the partial result is returned with
:attr:`PlaySearchResult.truncated` set, so the UI can say so instead of the tab
hanging.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from services.deck_patterns_service.castability import ManaUnit, can_pay
from services.deck_patterns_service.mana import ManaCost

#: How many search nodes one profile may visit before the result is truncated.
DEFAULT_NODE_BUDGET = 20_000

#: How many distinct maximal plays one profile may report.
DEFAULT_MAX_PLAYS = 40


@dataclass(frozen=True)
class Playable:
    """A nonland card the search may include, with how many copies exist."""

    name: str
    cost: ManaCost
    quantity: int

    @property
    def total(self) -> int:
        return self.cost.total


@dataclass(frozen=True)
class Play:
    """One maximal set of cards castable together."""

    #: ``(card name, copies)``, in the search's deterministic order.
    cards: tuple[tuple[str, int], ...]

    @property
    def copies(self) -> int:
        """How many cards are cast, counting duplicates."""
        return sum(count for _, count in self.cards)

    def as_text(self) -> str:
        return ", ".join(f"{count} {name}" for name, count in self.cards)


@dataclass
class PlaySearchResult:
    """The maximal plays for one mana profile."""

    plays: tuple[Play, ...] = ()
    truncated: bool = False
    nodes: int = 0


@dataclass
class PlaySearchCache:
    """Memoises :func:`maximal_plays` by mana profile.

    The cache is deliberately *not* global: it is owned by one computation run
    (one deck, one set of options), so a deck edit cannot serve a stale answer.
    """

    node_budget: int = DEFAULT_NODE_BUDGET
    max_plays: int = DEFAULT_MAX_PLAYS
    _entries: dict[tuple[ManaUnit, ...], PlaySearchResult] = field(default_factory=dict)
    hits: int = 0
    misses: int = 0

    def get(
        self, profile: tuple[ManaUnit, ...], playables: tuple[Playable, ...]
    ) -> PlaySearchResult:
        cached = self._entries.get(profile)
        if cached is not None:
            self.hits += 1
            return cached
        self.misses += 1
        result = maximal_plays(
            profile,
            playables,
            node_budget=self.node_budget,
            max_plays=self.max_plays,
        )
        self._entries[profile] = result
        return result


def maximal_plays(
    units: tuple[ManaUnit, ...],
    playables: tuple[Playable, ...],
    *,
    node_budget: int = DEFAULT_NODE_BUDGET,
    max_plays: int = DEFAULT_MAX_PLAYS,
) -> PlaySearchResult:
    """Every maximal castable multiset of ``playables`` payable by ``units``."""
    available = len(units)
    if not available or not playables:
        return PlaySearchResult()

    # Only cards that could ever be cast off this much mana are worth branching
    # on, and cheap-first ordering makes the mana prune bite sooner.
    candidates = tuple(
        sorted(
            (p for p in playables if p.total <= available and p.quantity > 0),
            key=lambda p: (p.total, p.name),
        )
    )
    if not candidates:
        return PlaySearchResult()

    state = {"nodes": 0, "truncated": False}
    found: list[tuple[tuple[str, int], ...]] = []
    seen: set[tuple[tuple[str, int], ...]] = set()

    def castable(selection: list[tuple[Playable, int]]) -> bool:
        costs: list[ManaCost] = []
        for playable, count in selection:
            costs.extend([playable.cost] * count)
        return can_pay(units, tuple(costs))

    def can_extend(selection: list[tuple[Playable, int]], spent: int) -> bool:
        """Whether any further copy could be added and stay castable."""
        for candidate in candidates:
            if candidate.total + spent > available:
                continue
            used = next((c for p, c in selection if p.name == candidate.name), 0)
            if used >= candidate.quantity:
                continue
            trial = [(p, c) for p, c in selection]
            for i, (p, c) in enumerate(trial):
                if p.name == candidate.name:
                    trial[i] = (p, c + 1)
                    break
            else:
                trial.append((candidate, 1))
            if castable(trial):
                return True
        return False

    def record(selection: list[tuple[Playable, int]], spent: int) -> None:
        if not selection:
            return
        key = tuple((p.name, c) for p, c in selection)
        if key in seen:
            return
        if can_extend(selection, spent):
            return
        seen.add(key)
        found.append(key)

    def walk(index: int, spent: int, selection: list[tuple[Playable, int]]) -> None:
        if state["truncated"]:
            return
        state["nodes"] += 1
        if state["nodes"] > node_budget or len(found) >= max_plays:
            state["truncated"] = True
            return
        if index >= len(candidates):
            record(selection, spent)
            return

        candidate = candidates[index]
        headroom = available - spent
        take_max = min(candidate.quantity, headroom // candidate.total) if candidate.total else 0

        for take in range(take_max, -1, -1):
            if take:
                selection.append((candidate, take))
                if castable(selection):
                    walk(index + 1, spent + take * candidate.total, selection)
                selection.pop()
            else:
                walk(index + 1, spent, selection)
            if state["truncated"]:
                return

    walk(0, 0, [])

    plays = tuple(Play(cards=cards) for cards in found)
    return PlaySearchResult(
        plays=plays,
        truncated=bool(state["truncated"]),
        nodes=int(state["nodes"]),
    )


__all__ = [
    "DEFAULT_MAX_PLAYS",
    "DEFAULT_NODE_BUDGET",
    "Play",
    "PlaySearchCache",
    "PlaySearchResult",
    "Playable",
    "maximal_plays",
]
