"""Debounced batch resolution of card metadata via Scryfall ``/cards/collection``.

On a *cold* start — a fresh install, before ``bulk_data.json`` has finished
downloading and the local image index exists — every card image request misses
the local index and needs a Scryfall metadata lookup to discover its image
URLs. Doing that one card at a time (``/cards/named`` per card) across the
download queue's concurrent workers is what tripped Scryfall's rate limiter and
produced the field symptom: a 429 storm that dropped a nondeterministic subset
of a deck's images on first run.

:class:`ScryfallBatchResolver` fixes that by *collecting the active fetch burst*:
resolution misses arriving within a short debounce window
(:data:`IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS`) are coalesced and resolved in one
``POST /cards/collection`` (up to :data:`SCRYFALL_COLLECTION_MAX_IDENTIFIERS`
identifiers per request, chunked). A window that collects exactly one card falls
back to the per-card ``/cards/named`` endpoint, since a batch of one has nothing
to batch. Identical identities arriving in the same window share one lookup.

The downloader only ever knows a card by ``name``, an optional ``set_code`` and
an optional ``uuid``, so collection identifiers are ``{"id": uuid}`` when a
printing is pinned (hover/inspector) and ``{"name": name}`` otherwise (the
common prefetch case). ``set_code`` precision is preserved on the single-card
``/cards/named`` path, which does accept a set filter.

Once the local index is warm (the steady state) resolution never reaches here,
so this path only carries the cold-start / not-in-bulk traffic.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable
from typing import Any

from loguru import logger

from services.image_service.printing_index import collect_name_aliases
from services.image_service.schemas import SCRYFALL_CARD_COLLECTION_URL
from utils.card_names import fold_card_name
from utils.constants import timing
from utils.constants.timing import (
    SCRYFALL_COLLECTION_MAX_IDENTIFIERS,
    SCRYFALL_REQUEST_TIMEOUT_SECONDS,
)

# A resolved card object (Scryfall JSON) or None when the identifier matched
# nothing. Callers treat None as a permanent "no such card" miss.
ResolvedCard = dict[str, Any] | None
FetchOne = Callable[[str, str | None], dict[str, Any]]


class _Entry:
    """One card's slot in a debounce window: its identity plus the result."""

    __slots__ = ("name", "set_code", "uuid", "result", "error", "done")

    def __init__(self, name: str, set_code: str | None, uuid: str | None) -> None:
        self.name = name
        self.set_code = set_code
        self.uuid = uuid
        self.result: ResolvedCard = None
        self.error: BaseException | None = None
        self.done = False

    def identifier(self) -> dict[str, str]:
        if self.uuid:
            return {"id": self.uuid}
        return {"name": self.name}


def _key(name: str, set_code: str | None, uuid: str | None) -> str:
    """Stable coalescing key: same identity → one shared lookup per window.

    Names are accent-folded so the ASCII spelling MTGO uses and the accented one
    Scryfall returns share a single lookup within a window.
    """
    if uuid:
        return f"id:{uuid.lower()}"
    if set_code:
        return f"set:{set_code.lower()}|{fold_card_name(name)}"
    return f"name:{fold_card_name(name)}"


def _is_not_found(exc: BaseException) -> bool:
    """Whether ``exc`` is Scryfall answering "no such card" rather than a blip.

    Only a 404 is an answer. A rate-limit, a timeout or a dropped connection
    says nothing about whether the card exists, and must not be filed as one —
    the queue treats "not found" as permanent for the rest of the session.
    """
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status is not None:
        return status == 404
    text = str(exc).lower()
    return "404" in text and "not found" in text


def _chunks(items: list[Any], size: int) -> Iterable[list[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class ScryfallBatchResolver:
    """Coalesce concurrent metadata-resolution misses into batched lookups."""

    def __init__(
        self,
        session,
        fetch_one: FetchOne,
        *,
        collection_url: str = SCRYFALL_CARD_COLLECTION_URL,
        chunk_size: int = SCRYFALL_COLLECTION_MAX_IDENTIFIERS,
        timeout: float = SCRYFALL_REQUEST_TIMEOUT_SECONDS,
        debounce: float | None = None,
    ) -> None:
        self._session = session
        self._fetch_one = fetch_one
        self._collection_url = collection_url
        self._chunk_size = chunk_size
        self._timeout = timeout
        # None → read the live constant each window so tests can monkeypatch it
        # and so the value isn't frozen at construction time.
        self._debounce = debounce
        self._cond = threading.Condition()
        self._pending: dict[str, _Entry] = {}
        self._window_active = False

    def resolve(
        self, name: str, set_code: str | None = None, uuid: str | None = None
    ) -> ResolvedCard:
        """Resolve one card's metadata, batched with any concurrent misses.

        Blocks the caller until its debounce window fires, then returns the
        Scryfall card object or ``None`` if the identifier matched nothing.
        Raises if the underlying lookup failed (network/HTTP error) so the
        download queue's existing retry/backoff handles it.
        """
        key = _key(name, set_code, uuid)
        with self._cond:
            entry = self._pending.get(key)
            if entry is None:
                entry = _Entry(name, set_code, uuid)
                self._pending[key] = entry
                if not self._window_active:
                    self._window_active = True
                    threading.Thread(
                        target=self._run_window,
                        name="scryfall-batch-resolve",
                        daemon=True,
                    ).start()
            while not entry.done:
                self._cond.wait()
        if entry.error is not None:
            raise entry.error
        return entry.result

    # ---------------------------------------------------------------- worker
    def _run_window(self) -> None:
        debounce = self._debounce
        if debounce is None:
            debounce = timing.IMAGE_BATCH_RESOLVE_DEBOUNCE_SECONDS
        if debounce > 0:
            time.sleep(debounce)
        with self._cond:
            batch = list(self._pending.values())
            self._pending = {}
            self._window_active = False
        self._resolve_batch(batch)
        with self._cond:
            for entry in batch:
                entry.done = True
            self._cond.notify_all()

    def _resolve_batch(self, entries: list[_Entry]) -> None:
        if not entries:
            return
        if len(entries) == 1:
            # A batch of one has nothing to batch: use the per-card endpoint,
            # which also preserves name+set precision for hover/inspector.
            entry = entries[0]
            try:
                entry.result = self._fetch_one(entry.name, entry.set_code)
            except Exception as exc:  # surfaced to the queue's retry loop
                entry.error = exc
            return
        try:
            cards = self._post_collection([e.identifier() for e in entries])
        except Exception as exc:
            logger.warning(f"Batched Scryfall resolution failed ({len(entries)} cards): {exc}")
            for entry in entries:
                entry.error = exc
            return
        index = _build_card_index(cards)
        requests_count = len(entries)
        logger.debug(
            f"Batched Scryfall resolution: {len(cards)} cards for {requests_count} requests "
            f"in {(requests_count - 1) // self._chunk_size + 1} request(s)"
        )
        for entry in entries:
            entry.result = _match_entry(entry, index)
        self._retry_unmatched(entries)

    def _retry_unmatched(self, entries: list[_Entry]) -> None:
        """Re-resolve name-only entries the collection lookup did not answer.

        ``/cards/collection`` matches a ``{"name": ...}`` identifier against
        Scryfall's card ``name`` only, so a card MTGO spells with its
        printing's ``printed_name`` — the Omenpaths "Universes Within" reprints
        — comes back in ``not_found`` and would be recorded as a permanent
        "no such card" (issue #986). The single-card path knows how to search
        by printed name, so the few unmatched names go through it. A miss there
        stays a miss, which is the pre-existing behaviour for a bogus name.

        A 404 there is still a miss. Anything else — a rate-limit, a timeout, a
        dropped connection — is *not*, and is recorded as an error so
        :meth:`resolve` re-raises it and the download queue retries it with
        backoff. Reporting those as ``None`` too made the caller phrase them as
        "404 not found", which the queue files as a permanent failure and never
        asks about again for the rest of the session (issue #986 follow-up).
        """
        for entry in entries:
            if entry.uuid or entry.result is not None:
                continue
            try:
                entry.result = self._fetch_one(entry.name, entry.set_code)
            except Exception as exc:
                logger.debug(f"Single-card fallback failed for {entry.name}: {exc}")
                if _is_not_found(exc):
                    entry.result = None
                else:
                    entry.error = exc

    def _post_collection(self, identifiers: list[dict[str, str]]) -> list[dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        for chunk in _chunks(identifiers, self._chunk_size):
            response = self._session.post(
                self._collection_url,
                json={"identifiers": chunk},
                timeout=self._timeout,
            )
            response.raise_for_status()
            cards.extend(response.json().get("data", []))
        return cards


def _build_card_index(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index resolved cards by every identity a request might carry.

    Keys: ``id:<uuid>`` and ``name:<name>`` plus one ``name:`` alias per
    face/split-half and per printed/flavor name — so a request that used a
    single face name, or the name MTGO prints on an Omenpaths "Universes
    Within" card (#986), still finds its card object. An alias never overwrites
    a real standalone card of that name (mirrors the local-index guard, #792).
    Every name key is then aliased under its accent-folded form: Scryfall
    resolves the ASCII name MTGO sent ("Gloin the Mighty") but answers with the
    accented one, so an exact-key match alone would drop the card as "not
    found".
    """
    index: dict[str, dict[str, Any]] = {}
    primary_names = {(card.get("name") or "").strip().lower() for card in cards if card.get("name")}
    for card in cards:
        name = (card.get("name") or "").strip()
        card_id = (card.get("id") or "").strip()
        if card_id:
            index.setdefault(f"id:{card_id.lower()}", card)
        if not name:
            continue
        index.setdefault(f"name:{name.lower()}", card)
        for alias in collect_name_aliases(card, name):
            alias_key = alias.lower()
            if alias_key not in primary_names:
                index.setdefault(f"name:{alias_key}", card)
    # Second pass so an exact name always wins over another card's folded form.
    for key, card in list(index.items()):
        if not key.startswith("name:"):
            continue
        folded = fold_card_name(key[len("name:") :])
        if folded:
            index.setdefault(f"name:{folded}", card)
    return index


def _match_entry(entry: _Entry, index: dict[str, dict[str, Any]]) -> ResolvedCard:
    if entry.uuid:
        return index.get(f"id:{entry.uuid.lower()}")
    exact = index.get(f"name:{(entry.name or '').lower()}")
    if exact is not None:
        return exact
    return index.get(f"name:{fold_card_name(entry.name)}")


__all__ = ["ScryfallBatchResolver"]
