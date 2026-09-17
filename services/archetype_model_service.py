"""Builds the game-log archetype model from the cached decklists.

Where the labelled decks come from
----------------------------------
Nothing new is downloaded. Three caches the app already keeps are joined:

- ``archetype_list.json`` -- per format, each archetype's display ``name`` and
  ``href``. It is the authority for which archetypes exist and in which format.
- ``archetype_decks_cache.json`` -- ``href -> items``, one item per decklist
  (MTGGoldfish scrapes and the remote bundle's MTGO decklists alike). The
  archetype label *is* the key the deck is filed under; the MTGO decklists'
  ``archetype`` field is not needed, because the bundle client files each deck
  under the href of exactly that archetype (and for those decks the stored
  ``name`` equals the ``archetype`` field anyway).
- ``deck_cache.db`` -- ``deck_number -> deck_text``.

Decks filed under an href that is no longer in the archetype list are skipped:
their label is one the app no longer shows anywhere, and the display name would
have to be guessed from a slug.

Why it runs in the background
-----------------------------
Measured on the real cache (2,573 labelled decks, 281 archetype clusters; a
6 MB deck index and a 12 MB deck-text database), seven fresh processes took a
median 0.46 s (max 0.46 s): ~0.24 s reading and parsing, ~0.21 s fitting. That is
over four times the 0.1 s a synchronous startup step is allowed, so
:meth:`ArchetypeModelService.start_background_build` runs it on a worker thread.
Inside the launching app it shares the CPU with the card-index and image-index
loads, and took ~4.4 s of wall time there. Until it finishes,
:meth:`wait_until_ready` lets a caller that is already off the UI thread
(match-history parsing) wait a bounded time, and every classification made
without a model returns ``"Unknown"``.
"""

from __future__ import annotations

import json
import re
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import msgspec
from loguru import logger

from services.gamelog_service.archetypes import ArchetypeModel, LabelledDeck
from utils.atomic_io import locked_path
from utils.constants import (
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    DECK_CACHE_DB_FILE,
)
from utils.format_keys import normalize_archetype_list_cache, normalize_format_key

if TYPE_CHECKING:
    from repositories.deck_text_cache import DeckTextCache

#: The formats a game log can be detected as (see
#: :mod:`services.gamelog_service.formats`); Commander and Brawl decklists in the
#: cache are left out so they cannot win a 60-card match.
MODEL_FORMATS: tuple[str, ...] = ("standard", "pioneer", "modern", "legacy", "vintage", "pauper")

#: Decklists with fewer maindeck cards than this are partial scrapes.
_MIN_MAINDECK_CARDS = 30

#: A trailing Scryfall printing id, stripped the way ``services.deck_service.parser`` does.
_PRINTING_ID_SUFFIX = re.compile(
    r"\s+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


class _DeckItem(msgspec.Struct, gc=False):
    number: str | int | None = None


class _DeckEntry(msgspec.Struct, gc=False):
    items: list[_DeckItem] = msgspec.field(default_factory=list)


# Decoding only the deck numbers skips every other field of a 6 MB document.
_decks_decoder = msgspec.json.Decoder(dict[str, _DeckEntry])


def parse_deck_text(text: str) -> tuple[dict[str, float], dict[str, float]]:
    """Split cached deck text into ``(mainboard, sideboard)`` name -> copies.

    The same layout rules as :class:`services.deck_service.parser.DeckParser`
    (``"4 Name"`` lines; a blank line or a ``Sideboard`` line starts the
    sideboard; a trailing Scryfall printing id is dropped), without its
    per-deck statistics, which were most of the model's build time.
    """
    mainboard: dict[str, float] = {}
    sideboard: dict[str, float] = {}
    target = mainboard
    for raw in text.strip().split("\n"):
        line = raw.strip()
        if not line or line.lower() == "sideboard":
            target = sideboard
            continue
        count, _, name = line.partition(" ")
        try:
            copies = float(count)
        except ValueError:
            continue
        name = name.strip()
        if len(name) > 37 and name[-13] == "-":
            name = _PRINTING_ID_SUFFIX.sub("", name)
        if name:
            target[name] = target.get(name, 0.0) + copies
    return mainboard, sideboard


class ArchetypeModelService:
    """Owns the archetype model: builds it off-thread and hands it to callers."""

    def __init__(
        self,
        archetype_list_file: Path = ARCHETYPE_LIST_CACHE_FILE,
        archetype_decks_file: Path = ARCHETYPE_DECKS_CACHE_FILE,
        deck_text_db_file: Path = DECK_CACHE_DB_FILE,
        formats: tuple[str, ...] = MODEL_FORMATS,
    ) -> None:
        self.archetype_list_file = Path(archetype_list_file)
        self.archetype_decks_file = Path(archetype_decks_file)
        self.deck_text_db_file = Path(deck_text_db_file)
        self.formats = formats
        self._model: ArchetypeModel | None = None
        # Serialises builds, so a rebuild requested mid-build reads the caches
        # again after the first one finishes instead of racing it.
        self._build_lock = threading.Lock()
        self._state = threading.Condition()
        self._pending_builds = 0
        self.last_build_seconds: float | None = None

    # ------------------------------------------------------------------ state
    @property
    def model(self) -> ArchetypeModel | None:
        return self._model

    @property
    def is_ready(self) -> bool:
        return self._model is not None

    def wait_until_ready(self, timeout: float) -> ArchetypeModel | None:
        """Return the model, waiting up to *timeout* s for an in-flight build.

        Returns at once when a model already exists (even if a rebuild is
        running -- the previous model is still a good answer) or when no build
        has been requested, so a caller never waits on a build nobody started.
        """
        deadline = time.monotonic() + max(timeout, 0.0)
        with self._state:
            while self._model is None and self._pending_builds > 0:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._state.wait(remaining)
            return self._model

    # ------------------------------------------------------------------ build
    def start_background_build(
        self, submit: Callable[[Callable[[], None]], Any] | None = None
    ) -> None:
        """Build (or rebuild) the model on a worker thread.

        *submit* hands the job to an existing worker (the controller passes its
        :class:`~utils.background_worker.BackgroundWorker`, so shutdown joins
        it); without one a daemon thread is used. The pending count is raised
        before the job is handed over, so :meth:`wait_until_ready` called right
        after this returns already knows a build is coming.
        """
        with self._state:
            self._pending_builds += 1

        def build_archetype_model() -> None:
            try:
                self.build()
            finally:
                with self._state:
                    self._pending_builds -= 1
                    self._state.notify_all()

        if submit is None:
            threading.Thread(
                target=build_archetype_model, name="archetype-model-build", daemon=True
            ).start()
        else:
            submit(build_archetype_model)

    def build(self) -> ArchetypeModel | None:
        """Load the labelled decks and fit a model, replacing the current one.

        Never raises. A failed build keeps the previous model (or none).
        """
        with self._build_lock:
            started = time.perf_counter()
            try:
                decks = self.load_labelled_decks()
                loaded = time.perf_counter()
                model = ArchetypeModel.build(decks)
            except Exception as exc:  # noqa: BLE001 - classification degrades to Unknown
                logger.warning(f"Archetype model build failed: {exc}")
                return None
            finished = time.perf_counter()
            with self._state:
                self._model = model
                self._state.notify_all()
            self.last_build_seconds = finished - started
            logger.info(
                f"Archetype model built in {finished - started:.3f}s "
                f"(load {loaded - started:.3f}s, fit {finished - loaded:.3f}s): "
                f"{model.deck_count} decks, {model.archetype_count} archetypes, "
                f"formats={','.join(model.formats) or 'none'}"
            )
            return model

    # ------------------------------------------------------------------ data
    def load_labelled_decks(self) -> list[LabelledDeck]:
        """Join the archetype list, the deck index and the deck texts."""
        archetypes = self._read_archetype_list()
        if not archetypes:
            return []
        numbers_by_href = self._read_deck_numbers(set(archetypes))
        texts = self._deck_text_cache().get_many(
            number for numbers in numbers_by_href.values() for number in numbers
        )

        decks: list[LabelledDeck] = []
        seen: set[str] = set()
        for href, numbers in numbers_by_href.items():
            mtg_format, name = archetypes[href]
            for number in numbers:
                text = texts.get(number)
                # A deck filed under two hrefs (a rename caught mid-refresh)
                # counts once, under the first.
                if not text or number in seen:
                    continue
                seen.add(number)
                mainboard, sideboard = parse_deck_text(text)
                if sum(mainboard.values()) < _MIN_MAINDECK_CARDS:
                    continue
                decks.append(
                    LabelledDeck(
                        mtg_format=mtg_format,
                        archetype=name,
                        mainboard=mainboard,
                        sideboard=sideboard,
                    )
                )
        return decks

    def _read_archetype_list(self) -> dict[str, tuple[str, str]]:
        """``href -> (format, name)`` for the formats the model covers."""
        try:
            with locked_path(self.archetype_list_file):
                raw = json.loads(self.archetype_list_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            logger.debug(f"Archetype list unavailable for the archetype model: {exc}")
            return {}
        result: dict[str, tuple[str, str]] = {}
        for fmt, entry in normalize_archetype_list_cache(raw).items():
            fmt_key = normalize_format_key(fmt)
            if fmt_key not in self.formats or not isinstance(entry, dict):
                continue
            for item in entry.get("items") or []:
                if not isinstance(item, dict):
                    continue
                href, name = item.get("href"), item.get("name")
                if isinstance(href, str) and href and isinstance(name, str) and name:
                    result[href] = (fmt_key, name)
        return result

    def _read_deck_numbers(self, hrefs: set[str]) -> dict[str, list[str]]:
        try:
            # The bundle client and the metagame repository write this file
            # under the same in-process lock; holding it while reading means a
            # hydration in progress is either wholly visible or not at all.
            with locked_path(self.archetype_decks_file):
                payload = self.archetype_decks_file.read_bytes()
            entries = _decks_decoder.decode(payload)
        except (OSError, msgspec.DecodeError, msgspec.ValidationError) as exc:
            logger.debug(f"Deck index unavailable for the archetype model: {exc}")
            return {}
        return {
            href: [str(item.number) for item in entry.items if item.number not in (None, "")]
            for href, entry in entries.items()
            if href in hrefs
        }

    def _deck_text_cache(self) -> DeckTextCache:
        from repositories.deck_text_cache import DeckTextCache, get_deck_cache

        if self.deck_text_db_file.resolve() == Path(DECK_CACHE_DB_FILE).resolve():
            return get_deck_cache()
        return DeckTextCache(db_path=self.deck_text_db_file)


_default_service: ArchetypeModelService | None = None


def get_archetype_model_service() -> ArchetypeModelService:
    """Return the shared :class:`ArchetypeModelService` instance."""
    global _default_service
    if _default_service is None:
        _default_service = ArchetypeModelService()
    return _default_service


def reset_archetype_model_service() -> None:
    """Reset the shared service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "MODEL_FORMATS",
    "ArchetypeModelService",
    "get_archetype_model_service",
    "reset_archetype_model_service",
]
