"""Turn-by-turn capability analysis for a decklist.

What the Patterns tab shows is a *ceiling*, not a projection: for each turn it
answers "if this deck's whole list were in hand, what could it do?" under the
two assumptions §2.1 fixes -- the full list is available, and each turn stands
alone with no board state, mana rocks or lands carried over from the turn
before. Turn ``M`` therefore means exactly "``M`` lands in play", which is why
no turn depends on any other and the turns can be computed independently.

The pipeline per turn: group the deck's lands by what they produce, enumerate
the count vectors of size ``M`` over those groups, collapse each onto a mana
profile, and run the maximal-play search once per distinct profile.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from services.deck_patterns_service.lands import (
    LandCombination,
    LandGroup,
    enumerate_combinations,
    group_lands,
)
from services.deck_patterns_service.mana import (
    LandProduction,
    parse_land_production,
    parse_mana_cost,
)
from services.deck_patterns_service.search import (
    DEFAULT_MAX_PLAYS,
    DEFAULT_NODE_BUDGET,
    Play,
    Playable,
    PlaySearchCache,
)

#: Default ceiling for the turn selector (§2.4 suggests 6-7).
DEFAULT_MAX_TURN = 7

#: How many land combinations one turn may report before it is truncated.
DEFAULT_MAX_COMBINATIONS = 60


@dataclass(frozen=True)
class CombinationResult:
    """One land combination and the maximal plays it allows."""

    combination: LandCombination
    plays: tuple[Play, ...]
    truncated: bool = False

    @property
    def label(self) -> str:
        return ", ".join(f"{count} {group.label}" for group, count in self.combination.entries())


@dataclass(frozen=True)
class TurnResult:
    """Everything computed for one turn."""

    turn: int
    combinations: tuple[CombinationResult, ...] = ()
    truncated: bool = False

    @property
    def playable_count(self) -> int:
        return sum(1 for c in self.combinations if c.plays)


@dataclass
class PatternsResult:
    """The whole analysis, plus how hard it was to get."""

    turns: tuple[TurnResult, ...] = ()
    land_groups: tuple[LandGroup, ...] = ()
    max_turn: int = DEFAULT_MAX_TURN
    cache_hits: int = 0
    cache_misses: int = 0

    @property
    def truncated(self) -> bool:
        return any(turn.truncated for turn in self.turns)

    def turn(self, number: int) -> TurnResult | None:
        return next((t for t in self.turns if t.turn == number), None)


@dataclass
class PatternsOptions:
    """Knobs for one run. All the §2.4 guardrails live here."""

    max_turn: int = DEFAULT_MAX_TURN
    max_combinations: int = DEFAULT_MAX_COMBINATIONS
    node_budget: int = DEFAULT_NODE_BUDGET
    max_plays: int = DEFAULT_MAX_PLAYS


@dataclass
class DeckPatternsService:
    """Computes a deck's capability ceiling. Holds no wx and no global state."""

    card_manager: Any = None
    _cache: PlaySearchCache | None = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------ card data ------------------------------------------------------------------
    def _resolve_manager(self) -> Any:
        """The card index, looked up late if it was not ready at construction.

        The frame builds this tab during start-up, when the atomic-cards index
        is still loading on a background thread, so whatever it passed in was
        almost certainly ``None`` -- and capturing that once meant every card
        looked unknown forever, which the tab reported as "no mana-producing
        land" for every deck. Resolving on use picks the index up as soon as it
        exists, and never forces the (expensive) load itself.
        """
        if self.card_manager is not None:
            return self.card_manager
        try:
            from repositories.card_repository import get_card_repository

            self.card_manager = get_card_repository().get_card_manager()
        except Exception:  # noqa: BLE001 - card data is best-effort here
            return None
        return self.card_manager

    def _card(self, name: str) -> Any:
        manager = self._resolve_manager()
        if manager is None:
            return None
        try:
            return manager.get_card(name)
        except Exception:  # noqa: BLE001 - card data is best-effort here
            return None

    def _is_land(self, meta: Any) -> bool:
        return "land" in ((meta.get("type_line") or "").lower() if meta else "")

    def split_deck(
        self, entries: list[dict[str, Any]]
    ) -> tuple[dict[str, tuple[int, LandProduction]], tuple[Playable, ...]]:
        """Split main-deck entries into lands (with production) and playables.

        A card with no card-data match is skipped rather than guessed at: it
        cannot be placed on either side without inventing a cost for it.
        """
        lands: dict[str, tuple[int, LandProduction]] = {}
        playables: list[Playable] = []

        for entry in entries:
            name = entry.get("name")
            qty = int(entry.get("qty") or 0)
            if not name or qty <= 0:
                continue
            meta = self._card(name)
            if meta is None:
                continue
            if self._is_land(meta):
                production = parse_land_production(meta.get("oracle_text"), meta.get("type_line"))
                if production.produces_mana:
                    previous = lands.get(name)
                    total = qty + (previous[0] if previous else 0)
                    lands[name] = (total, production)
                continue
            playables.append(
                Playable(name=name, cost=parse_mana_cost(meta.get("mana_cost")), quantity=qty)
            )

        return lands, tuple(playables)

    # ------------------------------------------------------------------ analysis ------------------------------------------------------------------
    def analyse(
        self,
        entries: list[dict[str, Any]],
        *,
        options: PatternsOptions | None = None,
        should_cancel: Callable[[], bool] | None = None,
        turns: Sequence[int] | None = None,
    ) -> PatternsResult:
        """Compute turns for ``entries`` (main-deck rows).

        ``turns`` selects which turns to compute; the default is all of
        1..``max_turn``. The UI passes the one turn it is about to show, because
        the cost of a turn climbs steeply with the number of land groups and
        computing six turns nobody asked for is what made a big mana base lock
        the tab up.
        """
        options = options or PatternsOptions()
        lands, playables = self.split_deck(entries)
        groups = group_lands(lands)

        cache = PlaySearchCache(node_budget=options.node_budget, max_plays=options.max_plays)
        self._cache = cache

        wanted = (
            tuple(range(1, max(1, options.max_turn) + 1))
            if turns is None
            else tuple(t for t in turns if t >= 1)
        )

        computed: list[TurnResult] = []
        for turn in wanted:
            if should_cancel is not None and should_cancel():
                break
            computed.append(
                self._analyse_turn(
                    turn, groups, playables, cache, options, should_cancel=should_cancel
                )
            )
        turns_result = computed

        return PatternsResult(
            turns=tuple(turns_result),
            land_groups=groups,
            max_turn=options.max_turn,
            cache_hits=cache.hits,
            cache_misses=cache.misses,
        )

    def _analyse_turn(
        self,
        turn: int,
        groups: tuple[LandGroup, ...],
        playables: tuple[Playable, ...],
        cache: PlaySearchCache,
        options: PatternsOptions,
        should_cancel: Callable[[], bool] | None = None,
    ) -> TurnResult:
        results: list[CombinationResult] = []
        truncated = False

        for combination in enumerate_combinations(groups, turn):
            if len(results) >= options.max_combinations:
                truncated = True
                break
            # A superseded run abandons the turn part-way rather than finishing
            # an answer nobody is waiting for.
            if should_cancel is not None and should_cancel():
                truncated = True
                break
            search = cache.get(combination.profile, playables)
            results.append(
                CombinationResult(
                    combination=combination,
                    plays=search.plays,
                    truncated=search.truncated,
                )
            )
            truncated = truncated or search.truncated

        return TurnResult(turn=turn, combinations=tuple(results), truncated=truncated)


_service: DeckPatternsService | None = None


def get_deck_patterns_service(card_manager: Any = None) -> DeckPatternsService:
    """Process-wide service instance, mirroring the other service accessors."""
    global _service
    if _service is None:
        _service = DeckPatternsService(card_manager=card_manager)
    elif card_manager is not None:
        _service.card_manager = card_manager
    return _service


def reset_deck_patterns_service() -> None:
    """Drop the singleton. Called by the test-suite global reset."""
    global _service
    _service = None


__all__ = [
    "DEFAULT_MAX_COMBINATIONS",
    "DEFAULT_MAX_TURN",
    "CombinationResult",
    "DeckPatternsService",
    "PatternsOptions",
    "PatternsResult",
    "TurnResult",
    "get_deck_patterns_service",
    "reset_deck_patterns_service",
]
