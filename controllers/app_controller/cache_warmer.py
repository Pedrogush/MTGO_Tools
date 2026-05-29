"""Lazy background warm-up of the decklist and card-image caches.

Two independent daemon threads, started a few seconds after the app finishes its
initial loads, progressively fill the on-disk caches so that the data a user is
most likely to open next is already local by the time they click:

* :meth:`CacheWarmer._warm_images` — for every archetype in every format, pick
  the archetype's most recent decklist and queue a card-image download for each
  card in it. The currently selected format is warmed first.

* :meth:`CacheWarmer._warm_decklists` — progressively hydrate the deck-text
  cache. First the headline list of each of the top few archetypes for *every*
  format (so all formats get a quick sample), then every list of the selected
  format, then every list of the remaining formats.

Both threads idle for :data:`CACHE_WARMUP_START_DELAY_SECONDS` before starting,
throttle between fetches, and check a shared stop event frequently so shutdown
interrupts them promptly. All the fetch/scrape calls they make are cache-first
(the metagame and deck-text caches dedupe), so a warm start is mostly skips and
the network cost is paid once.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator
from typing import Any

from loguru import logger

from services.image_service.schemas import CardImageRequest
from utils.constants.timing import (
    CACHE_WARMUP_JOIN_TIMEOUT_SECONDS,
    CACHE_WARMUP_START_DELAY_SECONDS,
    CACHE_WARMUP_THROTTLE_SECONDS,
    CACHE_WARMUP_TOP_DECKS_PER_FORMAT,
)

# Basic lands are trivially available, appear in nearly every deck, and would
# dominate the warm-up queue for no benefit, so the image warmer skips them.
_BASIC_LANDS = frozenset({"plains", "island", "swamp", "mountain", "forest", "wastes"})


class CacheWarmer:
    """Owns the two lazy warm-up threads and their lifecycle.

    Dependencies are injected as plain callables so the warmer can be unit
    tested without a controller, a wx app, or the network.
    """

    def __init__(
        self,
        *,
        get_current_format: Callable[[], str],
        formats: list[str],
        get_archetypes: Callable[[str], list[dict[str, Any]]],
        get_decks_for_archetype: Callable[[dict[str, Any]], list[dict[str, Any]]],
        download_deck_text: Callable[[dict[str, Any]], str],
        extract_card_names: Callable[[str], list[str]],
        enqueue_image: Callable[[CardImageRequest], None],
        start_delay: float = CACHE_WARMUP_START_DELAY_SECONDS,
        throttle: float = CACHE_WARMUP_THROTTLE_SECONDS,
        top_decks_per_format: int = CACHE_WARMUP_TOP_DECKS_PER_FORMAT,
    ) -> None:
        self._get_current_format = get_current_format
        self._formats = formats
        self._get_archetypes = get_archetypes
        self._get_decks_for_archetype = get_decks_for_archetype
        self._download_deck_text = download_deck_text
        self._extract_card_names = extract_card_names
        self._enqueue_image = enqueue_image
        self._start_delay = start_delay
        self._throttle = throttle
        self._top_decks_per_format = top_decks_per_format

        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        """Launch the two warm-up daemon threads (idempotent)."""
        if self._threads:
            return
        for name, target in (
            ("cache-warmer-images", self._warm_images),
            ("cache-warmer-decklists", self._warm_decklists),
        ):
            thread = threading.Thread(target=self._guard(target), name=name, daemon=True)
            self._threads.append(thread)
            thread.start()
        logger.debug("Cache warm-up threads started")

    def stop(self, timeout: float = CACHE_WARMUP_JOIN_TIMEOUT_SECONDS) -> None:
        """Signal the threads to stop and join them with a bounded wait."""
        self._stop_event.set()
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=timeout)
        self._threads = []

    # ------------------------------------------------------------------ helpers
    def _guard(self, target: Callable[[], None]) -> Callable[[], None]:
        """Wrap a thread body so an unexpected error never escapes the thread."""

        def runner() -> None:
            try:
                target()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"Cache warm-up thread {target.__name__} failed: {exc}")

        return runner

    def _stopped(self) -> bool:
        return self._stop_event.is_set()

    def _wait(self, seconds: float) -> bool:
        """Sleep, returning True if a stop was requested during the wait."""
        return self._stop_event.wait(seconds)

    def _ordered_formats(self) -> list[str]:
        """Return all formats with the selected one first (deduped, case-insensitive)."""
        selected = (self._get_current_format() or "").strip()
        ordered: list[str] = []
        seen: set[str] = set()
        for fmt in [selected, *self._formats]:
            key = fmt.lower()
            if fmt and key not in seen:
                seen.add(key)
                ordered.append(fmt)
        return ordered

    def _safe_archetypes(self, fmt: str) -> list[dict[str, Any]]:
        try:
            return self._get_archetypes(fmt) or []
        except Exception as exc:
            logger.debug(f"Warm-up: failed to load archetypes for {fmt}: {exc}")
            return []

    def _safe_decks(self, archetype: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return self._get_decks_for_archetype(archetype) or []
        except Exception as exc:
            logger.debug(f"Warm-up: failed to load decks for {archetype.get('name')}: {exc}")
            return []

    def _safe_deck_text(self, deck: dict[str, Any]) -> str:
        try:
            return self._download_deck_text(deck) or ""
        except Exception as exc:
            logger.debug(f"Warm-up: failed to fetch deck {deck.get('number')}: {exc}")
            return ""

    def _iter_format_decks(
        self, fmt: str, *, per_archetype: int | None, limit: int | None
    ) -> Iterator[dict[str, Any]]:
        """Yield decks for ``fmt`` by walking archetypes in metagame order.

        ``per_archetype`` caps how many decks to take from each archetype;
        ``limit`` caps the total yielded across the format. ``None`` means
        unbounded. Stops early when a stop is requested.
        """
        yielded = 0
        for archetype in self._safe_archetypes(fmt):
            if self._stopped() or (limit is not None and yielded >= limit):
                return
            decks = self._safe_decks(archetype)
            for deck in decks[:per_archetype] if per_archetype is not None else decks:
                if self._stopped() or (limit is not None and yielded >= limit):
                    return
                yield deck
                yielded += 1

    # ------------------------------------------------------------------ thread A: images
    def _warm_images(self) -> None:
        if self._wait(self._start_delay):
            return
        logger.debug("Cache warm-up: starting image pre-fetch")
        count = 0
        for fmt in self._ordered_formats():
            if self._stopped():
                return
            for archetype in self._safe_archetypes(fmt):
                if self._stopped():
                    return
                decks = self._safe_decks(archetype)
                if not decks:
                    continue
                # Pick the archetype's most recent decklist (decks are sorted
                # date-descending) and warm an image for each of its cards.
                deck_text = self._safe_deck_text(decks[0])
                if not deck_text:
                    continue
                for name in self._card_names(deck_text):
                    if self._stopped():
                        return
                    self._queue_image(name)
                    count += 1
                if self._wait(self._throttle):
                    return
        logger.info(f"Cache warm-up: image pre-fetch complete ({count} cards queued)")

    def _card_names(self, deck_text: str) -> list[str]:
        names: list[str] = []
        seen: set[str] = set()
        for name in self._extract_card_names(deck_text):
            key = name.lower()
            if key in seen or key in _BASIC_LANDS:
                continue
            seen.add(key)
            names.append(name)
        return names

    def _queue_image(self, card_name: str) -> None:
        try:
            self._enqueue_image(
                CardImageRequest(
                    card_name=card_name,
                    uuid=None,
                    set_code=None,
                    collector_number=None,
                    size="normal",
                )
            )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug(f"Warm-up: failed to queue image for {card_name}: {exc}")

    # ------------------------------------------------------------------ thread B: decklists
    def _warm_decklists(self) -> None:
        if self._wait(self._start_delay):
            return
        logger.debug("Cache warm-up: starting decklist pre-fetch")
        formats = self._ordered_formats()
        if not formats:
            return
        warmed: set[str] = set()

        # Phase 1: the headline list of the top few archetypes for *every*
        # format, so all formats get a quick representative sample first.
        for fmt in formats:
            if self._stopped():
                return
            for deck in self._iter_format_decks(
                fmt, per_archetype=1, limit=self._top_decks_per_format
            ):
                if self._warm_deck(deck, warmed):
                    return

        # Phase 2: every list of the selected format.
        for deck in self._iter_format_decks(formats[0], per_archetype=None, limit=None):
            if self._warm_deck(deck, warmed):
                return

        # Phase 3: every list of the remaining formats.
        for fmt in formats[1:]:
            for deck in self._iter_format_decks(fmt, per_archetype=None, limit=None):
                if self._warm_deck(deck, warmed):
                    return

        logger.info(f"Cache warm-up: decklist pre-fetch complete ({len(warmed)} lists)")

    def _warm_deck(self, deck: dict[str, Any], warmed: set[str]) -> bool:
        """Hydrate one deck's text into the cache. Returns True if it should stop."""
        if self._stopped():
            return True
        number = str(deck.get("number") or "")
        if number and number in warmed:
            return False
        self._safe_deck_text(deck)
        if number:
            warmed.add(number)
        return self._wait(self._throttle)
