"""Archetype baselines, as the rest of the app uses them.

Two jobs live here. The first is computing a baseline from a pool of decks that
share an archetype and format -- the pool comes from data the app already
ingests (``MetagameRepository`` for the deck records, ``DeckTextCache`` for
their decklists), so nothing here scrapes anything.

The second is seeding a new deck's version history with that baseline as its
root commit, which is what turns "diff against the archetype baseline" into an
ordinary diff against an ancestor. The rule that makes it safe is that the root
is written once, when the deck first gets a history, and never afterwards: see
:mod:`repositories.deck_vcs_repository.baseline` for why re-rooting is refused
rather than merely discouraged.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Any

from loguru import logger

from services.archetype_baseline_service.classify import build_baseline
from services.archetype_baseline_service.models import ArchetypeBaseline
from services.archetype_baseline_service.store import BaselineStore

if TYPE_CHECKING:
    from repositories.deck_vcs_repository import DeckVcsRepository

#: Below this many decks a baseline is arithmetic rather than evidence.
#:
#: A strict intersection fails in the *opposite* direction to a threshold: it is
#: small pools that produce implausibly *large* baselines, because a pool of one
#: deck is its own intersection and reports all 60 cards as settled archetype
#: consensus. Each additional list can only ever remove cards, so the number
#: here is really "how many independent lists must agree before agreement means
#: anything". Eight is the point where a baseline stops looking like one
#: player's deck; it is a judgement call, not a derived constant.
MIN_POOL_SIZE = 8


class ArchetypeBaselineService:
    """Compute, store and apply archetype baselines."""

    def __init__(
        self,
        *,
        metagame_repo: Any = None,
        deck_cache: Any = None,
        vcs_repo: DeckVcsRepository | None = None,
        store: BaselineStore | None = None,
        text_provider: Callable[[Sequence[str]], dict[str, str]] | None = None,
    ) -> None:
        self._metagame_repo = metagame_repo
        self._deck_cache = deck_cache
        self._vcs_repo = vcs_repo
        self.store = store or BaselineStore()
        self._text_provider = text_provider

    # ------------------------------------------------------------------ lazy deps ------------------------------------------------------------------
    @property
    def metagame_repo(self) -> Any:
        if self._metagame_repo is None:
            from repositories.metagame_repository import get_metagame_repository

            self._metagame_repo = get_metagame_repository()
        return self._metagame_repo

    @property
    def deck_cache(self) -> Any:
        if self._deck_cache is None:
            from repositories.deck_text_cache import get_deck_cache

            self._deck_cache = get_deck_cache()
        return self._deck_cache

    @property
    def vcs_repo(self) -> DeckVcsRepository:
        if self._vcs_repo is None:
            from repositories.deck_vcs_repository import get_deck_vcs_repository

            self._vcs_repo = get_deck_vcs_repository()
        return self._vcs_repo

    # ------------------------------------------------------------------ pool ------------------------------------------------------------------
    def pool_texts(
        self,
        archetype: dict[str, Any],
        *,
        source_filter: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[str], list[str]]:
        """``(deck_texts, deck_numbers)`` for the archetype's cached decks.

        Only decklists already in the text cache are used. A baseline is a
        summary of what has been collected, and downloading a pool's worth of
        lists inline would turn one click into dozens of round trips -- the
        research panel is what fills that cache, on purpose.
        """
        decks = self.metagame_repo.get_decks_for_archetype(archetype, source_filter=source_filter)
        numbers = [str(deck.get("number") or deck.get("href") or "") for deck in decks]
        numbers = [number for number in numbers if number]
        if limit is not None:
            numbers = numbers[:limit]
        if not numbers:
            return ([], [])

        if self._text_provider is not None:
            texts_by_number = self._text_provider(numbers)
        else:
            texts_by_number = self.deck_cache.get_many(numbers)

        ordered_numbers = [number for number in numbers if texts_by_number.get(number)]
        texts = [texts_by_number[number] for number in ordered_numbers]
        logger.info(
            f"Baseline pool for {archetype.get('name', '?')}: "
            f"{len(texts)} decklists from {len(numbers)} decks"
        )
        return (texts, ordered_numbers)

    # ------------------------------------------------------------------ computing ------------------------------------------------------------------
    def compute(
        self,
        archetype: dict[str, Any],
        *,
        mtg_format: str,
        source_filter: str | None = None,
        limit: int | None = None,
        persist: bool = True,
    ) -> ArchetypeBaseline | None:
        """Compute (and by default store) the baseline for one archetype.

        Returns ``None`` when the pool is too small to mean anything -- see
        :data:`MIN_POOL_SIZE`.
        """
        name = str(archetype.get("name") or "Unknown")
        texts, numbers = self.pool_texts(archetype, source_filter=source_filter, limit=limit)
        if len(texts) < MIN_POOL_SIZE:
            logger.info(f"Baseline for {name}: pool of {len(texts)} is below {MIN_POOL_SIZE}")
            return None

        baseline = build_baseline(
            texts,
            archetype=name,
            mtg_format=mtg_format,
            sources=tuple(numbers),
        )
        if persist:
            self.store.save(baseline)
        return baseline

    def stored(self, archetype: str, mtg_format: str) -> ArchetypeBaseline | None:
        return self.store.get(archetype, mtg_format)

    # ------------------------------------------------------------------ root commit ------------------------------------------------------------------
    def seed_root_for_new_deck(
        self,
        deck_key: str,
        *,
        archetype: str | None,
        mtg_format: str | None,
    ) -> str | None:
        """Root ``deck_key``'s history at its archetype baseline, if there is one.

        Returns the root sha, or ``None`` when there is no stored baseline for
        the archetype/format or the deck already has history. Callers treat this
        as best effort: a deck without a baseline root is an ordinary deck whose
        history simply starts at its first save.
        """
        if not archetype or not mtg_format:
            return None
        if self.vcs_repo.has_repo(deck_key) and any(
            True for _ in self.vcs_repo.iter_commits(deck_key)
        ):
            return None

        baseline = self.stored(archetype, mtg_format)
        if baseline is None:
            return None

        text = baseline.decklist()
        if not text.strip():
            return None

        from repositories.deck_vcs_repository.baseline import BaselineRootError

        try:
            return self.vcs_repo.seed_baseline_root(
                deck_key,
                text,
                archetype=baseline.archetype,
                mtg_format=baseline.mtg_format,
            )
        except BaselineRootError as exc:
            logger.warning(f"Could not root {deck_key} at its baseline: {exc}")
            return None

    def root_sha(self, deck_key: str) -> str | None:
        """The deck's root commit -- what "diff vs. baseline" pins to."""
        return self.vcs_repo.root_commit_sha(deck_key)

    def has_baseline_root(self, deck_key: str) -> bool:
        sha = self.root_sha(deck_key)
        return bool(sha) and self.vcs_repo.is_baseline_root(deck_key, str(sha))


_default_service: ArchetypeBaselineService | None = None


def get_archetype_baseline_service() -> ArchetypeBaselineService:
    global _default_service
    if _default_service is None:
        _default_service = ArchetypeBaselineService()
    return _default_service


def reset_archetype_baseline_service() -> None:
    """Reset the global baseline service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "MIN_POOL_SIZE",
    "ArchetypeBaselineService",
    "get_archetype_baseline_service",
    "reset_archetype_baseline_service",
]
