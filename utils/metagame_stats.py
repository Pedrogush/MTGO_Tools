"""Aggregate MTGO metagame data from mtgo.com decklists."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any

from loguru import logger

from navigators.mtgo_decklists import fetch_deck_event, fetch_decklist_index
from utils.archetype_classifier import ArchetypeClassifier
from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import MTGO_DECK_CACHE_FILE, MTGO_DECKLISTS_ENABLED

try:
    from datetime import UTC
except ImportError:
    UTC = timezone.utc  # noqa: UP017

_FILTER_TOLERANCE = timedelta(seconds=5)


def _load_cache() -> dict[str, Any]:
    if not MTGO_DECK_CACHE_FILE.exists():
        return {}
    try:
        with locked_path(MTGO_DECK_CACHE_FILE):
            with MTGO_DECK_CACHE_FILE.open("r", encoding="utf-8") as fh:
                return json.load(fh)
    except json.JSONDecodeError as exc:
        logger.warning(f"Invalid deck cache JSON: {exc}")
        return {}


def _save_cache(cache: dict[str, Any]) -> None:
    atomic_write_json(MTGO_DECK_CACHE_FILE, cache, indent=2)


def _parse_iso(date_str: str | None) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            logger.debug(f"Unable to parse date string: {date_str}")
            return None


def update_mtgo_deck_cache(
    days: int = 7,
    fmt: str | None = None,
    max_events: int = 40,
) -> list[dict[str, Any]]:
    """Fetch recent MTGO decklists from mtgo.com and cache them locally."""
    if not MTGO_DECKLISTS_ENABLED:
        logger.info("MTGO decklists disabled; skipping cache update.")
        return []

    now = datetime.now(UTC)
    start = now - timedelta(days=days)

    with locked_path(MTGO_DECK_CACHE_FILE):
        cache = _load_cache()
        snapshots = cache.setdefault("snapshots", {})
        snapshot_key = f"{(fmt or 'all').lower()}::{days}"
        snapshot = snapshots.get(snapshot_key)
        if snapshot and now.timestamp() - snapshot.get("updated_at", 0) < 60 * 30:
            return snapshot.get("decks", [])

        existing_events = cache.get("events", {})
        aggregated: list[dict[str, Any]] = []

        months: set[tuple[int, int]] = set()
        probe = start
        while probe <= now:
            months.add((probe.year, probe.month))
            probe += timedelta(days=1)

        seen_urls: set[str] = set()
        total_events = 0
        for year, month in sorted(months):
            try:
                entries = fetch_decklist_index(year, month)
            except Exception as exc:
                logger.error(f"Failed to fetch MTGO decklist index {year}-{month:02d}: {exc}")
                continue

            entry_by_url: dict[str, dict[str, Any]] = {}
            entry_payloads: dict[str, Any] = {}
            pending_entries: dict[str, dict[str, Any]] = {}
            for entry in entries:
                if max_events and (total_events + len(entry_by_url)) >= max_events:
                    break
                if fmt:
                    entry_fmt = (entry.get("format") or "").lower()
                    if entry_fmt and entry_fmt != fmt.lower():
                        continue
                publish_date = _parse_iso(entry.get("publish_date"))
                if not publish_date:
                    continue
                if publish_date.tzinfo is None:
                    publish_date = publish_date.replace(tzinfo=UTC)
                if not (start <= publish_date <= now):
                    continue
                url = entry.get("url")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                payload = existing_events.get(url)
                if payload is None:
                    pending_entries[url] = entry
                else:
                    entry_payloads[url] = payload
                entry_by_url[url] = entry

            if pending_entries:
                max_workers = min(5, len(pending_entries))
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_map = {
                        executor.submit(fetch_deck_event, url): url for url in pending_entries
                    }
                    for future in as_completed(future_map):
                        url = future_map[future]
                        try:
                            payload = future.result()
                        except Exception as exc:
                            logger.error(f"Failed to fetch deck event {url}: {exc}")
                            continue
                        entry_payloads[url] = payload
                        existing_events[url] = payload

            for url, entry in entry_by_url.items():
                payload = entry_payloads.get(url)
                if not payload:
                    continue
                publish_date = _parse_iso(entry.get("publish_date")) or now
                if publish_date.tzinfo is None:
                    publish_date = publish_date.replace(tzinfo=UTC)
                event_name = payload.get("name") or entry.get("title")
                decks = payload.get("decklists", [])
                for deck in decks:
                    mainboard = _convert_cards(deck.get("main_deck", []))
                    sideboard = _convert_cards(deck.get("sideboard_deck", []))
                    archetype = deck.get("archetype") or entry.get("title")
                    final_format = entry.get("format") or fmt or "Unknown"
                    aggregated.append(
                        {
                            "event_url": url,
                            "event_name": event_name,
                            "publish_date": publish_date.isoformat(),
                            "event_type": entry.get("event_type"),
                            "format": final_format,
                            "deck_name": archetype,
                            "player": deck.get("player"),
                            "archetype": archetype,
                            "mainboard": mainboard,
                            "sideboard": sideboard,
                        }
                    )
                total_events += 1
                if max_events and total_events >= max_events:
                    break

            if max_events and total_events >= max_events:
                break

        if aggregated:
            classifier = ArchetypeClassifier()
            target_formats: set[str] = set()
            if fmt:
                target_formats.add(fmt)
            else:
                target_formats = {deck.get("format") for deck in aggregated if deck.get("format")}
            for format_name in sorted(filter(None, target_formats)):
                try:
                    classifier.assign_archetypes(aggregated, format_name)
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"Failed to classify archetypes for {format_name}: {exc}")

            for deck in aggregated:
                archetype = (deck.get("archetype") or "").strip()
                event_label = (deck.get("event_name") or "").strip()
                if not archetype:
                    deck["archetype"] = "Unknown"
                elif event_label and archetype.lower() == event_label.lower():
                    deck["archetype"] = "Unknown"

        snapshots[snapshot_key] = {
            "updated_at": time.time(),
            "decks": aggregated,
        }
        cache["snapshots"] = snapshots
        cache["events"] = existing_events
        _save_cache(cache)
        return aggregated


def load_aggregated_decks() -> list[dict[str, Any]]:
    cache = _load_cache()
    snapshots = cache.get("snapshots", {})
    if not snapshots:
        aggregated = cache.get("aggregated", {})
        return aggregated.get("decks", [])
    latest_key = max(snapshots, key=lambda k: snapshots[k].get("updated_at", 0), default=None)
    if latest_key is None:
        return []
    return snapshots[latest_key].get("decks", [])


def _filter_decks(
    decks: Iterable[dict[str, Any]],
    event_type: str | None = None,
    fmt: str | None = None,
    days: int | None = None,
) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    window = timedelta(days=days) if days is not None else None
    window_with_tolerance = (window + _FILTER_TOLERANCE) if window is not None else None

    filtered: list[dict[str, Any]] = []
    for deck in decks:
        if event_type and deck.get("event_type") != event_type:
            continue
        if fmt and (deck.get("format") or "").lower() != fmt.lower():
            continue
        if window_with_tolerance is not None:
            publish = _parse_iso(deck.get("publish_date"))
            if not publish:
                continue
            if publish.tzinfo is None:
                publish = publish.replace(tzinfo=UTC)
            if now - publish > window_with_tolerance:
                continue
        filtered.append(deck)
    return filtered


def count_decks_by_archetype(
    decks: Iterable[dict[str, Any]],
    event_type: str | None = None,
    fmt: str | None = None,
    days: int | None = None,
) -> list[tuple[str, int]]:
    filtered = _filter_decks(decks, event_type=event_type, fmt=fmt, days=days)
    counter = Counter()
    for deck in filtered:
        archetype = deck.get("archetype") or deck.get("deck_name") or "Unknown"
        counter[archetype] += 1
    return counter.most_common()


def count_decks_by_player(
    decks: Iterable[dict[str, Any]],
    event_type: str | None = None,
    fmt: str | None = None,
    days: int | None = None,
) -> list[tuple[str, int]]:
    filtered = _filter_decks(decks, event_type=event_type, fmt=fmt, days=days)
    counter = Counter()
    for deck in filtered:
        player = deck.get("player") or "Unknown"
        counter[player] += 1
    return counter.most_common()


def count_decks_by_event(
    decks: Iterable[dict[str, Any]],
    fmt: str | None = None,
    days: int | None = None,
) -> list[tuple[str, int]]:
    filtered = _filter_decks(decks, fmt=fmt, days=days)
    counter = Counter()
    for deck in filtered:
        label = deck.get("event_name") or deck.get("event_type") or "Unknown"
        counter[label] += 1
    return counter.most_common()


def summarize_meta_share(
    decks: Iterable[dict[str, Any]],
    event_type: str | None = None,
    days: int | None = None,
) -> dict[str, Counter]:
    filtered = _filter_decks(decks, event_type=event_type, days=days)
    result: dict[str, Counter] = defaultdict(Counter)
    for deck in filtered:
        fmt = deck.get("format") or "Unknown"
        archetype = deck.get("archetype") or deck.get("deck_name") or "Unknown"
        result[fmt][archetype] += 1
    return result


def _convert_cards(cards: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for card in cards or []:
        qty = card.get("qty") or card.get("quantity") or 0
        try:
            count = int(qty)
        except (TypeError, ValueError):
            count = 0
        attrs = card.get("card_attributes") or {}
        name = attrs.get("card_name") or card.get("card_name")
        if not name:
            continue
        converted.append({"name": name, "count": count})
    return converted


def aggregate_archetypes_for_window(
    decks: Iterable[dict[str, Any]],
    fmt: str | None = None,
    days: int = 1,
) -> dict[str, int]:
    """Aggregate archetype counts for a time window."""
    filtered = _filter_decks(decks, fmt=fmt, days=days)
    counter = Counter()
    for deck in filtered:
        archetype = deck.get("archetype") or deck.get("deck_name") or "Unknown"
        counter[archetype] += 1
    return dict(counter)


def calculate_metagame_percentages(
    archetype_counts: dict[str, int],
) -> dict[str, float]:
    """Calculate percentage share for each archetype."""
    total = sum(archetype_counts.values())
    if total == 0:
        return {}
    return {archetype: (count / total) * 100 for archetype, count in archetype_counts.items()}


def calculate_metagame_changes(
    current_period: dict[str, int],
    previous_period: dict[str, int],
) -> dict[str, float]:
    """Calculate percentage point changes between two time periods."""
    current_pct = calculate_metagame_percentages(current_period)
    previous_pct = calculate_metagame_percentages(previous_period)
    all_archetypes = set(current_pct.keys()) | set(previous_pct.keys())
    changes = {}
    for archetype in all_archetypes:
        current = current_pct.get(archetype, 0.0)
        previous = previous_pct.get(archetype, 0.0)
        changes[archetype] = current - previous
    return changes


__all__ = [
    "update_mtgo_deck_cache",
    "load_aggregated_decks",
    "count_decks_by_archetype",
    "count_decks_by_player",
    "count_decks_by_event",
    "summarize_meta_share",
    "aggregate_archetypes_for_window",
    "calculate_metagame_percentages",
    "calculate_metagame_changes",
]
