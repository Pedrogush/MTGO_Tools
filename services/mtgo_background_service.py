"""Background service for fetching MTGO data."""

import json
import time
from datetime import datetime, timedelta

try:
    from datetime import UTC
except ImportError:  # pragma: no cover - Python 3.10 fallback
    UTC = UTC

from loguru import logger

from navigators.mtgo_decklists import fetch_deck_event, fetch_decklist_index
from utils.archetype_classifier import ArchetypeClassifier
from utils.constants import (
    MTGO_BACKGROUND_FETCH_DAYS,
    MTGO_BACKGROUND_FETCH_DELAY_SECONDS,
    MTGO_DECKLISTS_ENABLED,
    MTGO_METADATA_CACHE_FILE,
)
from utils.deck_text_cache import get_deck_cache

MTGO_METADATA_CACHE = MTGO_METADATA_CACHE_FILE


def _mtgo_feature_disabled(message: str) -> bool:
    if not MTGO_DECKLISTS_ENABLED:
        logger.info(f"MTGO decklists disabled; {message}")
        return True
    return False


def parse_mtgo_deck(raw_deck: dict) -> dict:
    """Parse raw MTGO deck into clean simplified format."""
    deck_id = raw_deck.get("loginplayeventcourseid") or raw_deck.get("decktournamentid")
    player = raw_deck.get("player") or raw_deck.get("pilot") or "Unknown"

    wins_data = raw_deck.get("wins", {})
    if isinstance(wins_data, dict):
        wins = wins_data.get("wins", "5")
        losses = wins_data.get("losses", "0")
    else:
        wins = "5"
        losses = "0"

    mainboard = []
    for card in raw_deck.get("main_deck", []):
        if card.get("sideboard") == "false":
            card_name = card.get("card_attributes", {}).get("card_name", "")
            if card_name:
                mainboard.append(
                    {"card_name": card_name, "qty": int(card.get("qty", "1")), "sideboard": "false"}
                )

    sideboard = []
    for card in raw_deck.get("sideboard_deck", []):
        card_name = card.get("card_attributes", {}).get("card_name", "")
        if card_name:
            sideboard.append(
                {"card_name": card_name, "qty": int(card.get("qty", "1")), "sideboard": "true"}
            )

    return {
        "deck_id": deck_id,
        "player": player,
        "wins": wins,
        "losses": losses,
        "mainboard": mainboard,
        "sideboard": sideboard,
    }


def convert_deck_to_classifier_format(clean_deck: dict) -> dict:
    """Convert clean deck format to ArchetypeClassifier format."""
    mainboard = [
        {"name": card["card_name"], "count": card["qty"]} for card in clean_deck["mainboard"]
    ]
    sideboard = [
        {"name": card["card_name"], "count": card["qty"]} for card in clean_deck["sideboard"]
    ]

    return {"mainboard": mainboard, "sideboard": sideboard, "format": "modern"}


def deck_to_text(clean_deck: dict) -> str:
    """Convert clean deck format to text format."""
    lines = []

    for card in clean_deck["mainboard"]:
        lines.append(f"{card['qty']} {card['card_name']}")

    lines.append("sideboard")

    for card in clean_deck["sideboard"]:
        lines.append(f"{card['qty']} {card['card_name']}")

    return "\n".join(lines) + "\n"


def save_mtgo_deck_metadata(archetype: str, mtg_format: str, deck_metadata: dict) -> None:
    """
    Save MTGO deck metadata to JSON cache.

    Args:
        archetype: Archetype name
        mtg_format: Format (e.g., "modern")
        deck_metadata: Deck metadata dictionary
    """
    if _mtgo_feature_disabled("skip saving deck metadata"):
        return

    cache_key = f"{mtg_format}:{archetype}"

    try:
        if MTGO_METADATA_CACHE.exists():
            try:
                with MTGO_METADATA_CACHE.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except json.JSONDecodeError:
                logger.warning("MTGO metadata cache invalid JSON; resetting file")
                data = {}
        else:
            data = {}

        if cache_key not in data:
            data[cache_key] = []

        deck_id = deck_metadata.get("number")
        existing_ids = {d.get("number") for d in data[cache_key]}
        if deck_id not in existing_ids:
            data[cache_key].append(deck_metadata)

        MTGO_METADATA_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with MTGO_METADATA_CACHE.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)

    except Exception as exc:
        logger.error(f"Failed to save MTGO deck metadata: {exc}")
        raise


def load_mtgo_deck_metadata(archetype: str, mtg_format: str) -> list[dict]:
    """
    Load MTGO deck metadata from JSON cache.

    Args:
        archetype: Archetype name
        mtg_format: Format (e.g., "modern")

    Returns:
        List of deck metadata dictionaries
    """
    if _mtgo_feature_disabled("returning no cached metadata"):
        return []

    cache_key = f"{mtg_format}:{archetype}"

    try:
        if not MTGO_METADATA_CACHE.exists():
            return []

        try:
            with MTGO_METADATA_CACHE.open("r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError:
            logger.warning("MTGO metadata cache invalid JSON; returning empty results")
            return []

        return data.get(cache_key, [])

    except Exception as exc:
        logger.warning(f"Failed to load MTGO deck metadata: {exc}")
        return []


def fetch_mtgo_events_for_period(
    start_date: datetime, end_date: datetime, mtg_format: str = "modern"
):
    """
    Fetch MTGO events between start_date and end_date.

    Returns list of event URLs.
    """
    if _mtgo_feature_disabled("skipping fetch_mtgo_events_for_period"):
        return []

    logger.info(
        f"Fetching MTGO events for {mtg_format} from {start_date.date()} to {end_date.date()}"
    )
    events = []
    current_date = start_date

    logger.info(
        f"Starting loop: current_date={current_date.date()}, end_date={end_date.date()}, condition={current_date <= end_date}"
    )
    while current_date <= end_date:
        logger.info(f"Loop iteration for {current_date.year}-{current_date.month:02d}")
        try:
            logger.info(f"Calling fetch_decklist_index({current_date.year}, {current_date.month})")
            entries = fetch_decklist_index(current_date.year, current_date.month)
            logger.info(
                f"fetch_decklist_index returned {len(entries)} total entries for {current_date.year}-{current_date.month:02d}"
            )

            # Filter for the format and date range
            matching_entries = 0
            for entry in entries:
                if not entry.get("format"):
                    continue

                if mtg_format.lower() not in entry["format"].lower():
                    continue

                # Parse publish date
                try:
                    publish_date_str = entry.get("publish_date", "")
                    if publish_date_str:
                        publish_date = datetime.fromisoformat(
                            publish_date_str.replace("Z", "+00:00")
                        )
                        if start_date <= publish_date <= end_date:
                            events.append(
                                {
                                    "url": entry["url"],
                                    "title": entry["title"],
                                    "date": entry["publish_date"],
                                    "event_type": entry.get("event_type", "unknown"),
                                }
                            )
                            matching_entries += 1
                except (ValueError, AttributeError):
                    pass

            logger.info(
                f"Found {matching_entries} {mtg_format} events in date range for {current_date.year}-{current_date.month:02d}"
            )

            # Move to next month if needed
            if current_date.month == 12:
                current_date = datetime(current_date.year + 1, 1, 1, tzinfo=UTC)
            else:
                current_date = datetime(current_date.year, current_date.month + 1, 1, tzinfo=UTC)

        except Exception as exc:
            logger.error(
                f"Failed to fetch events for {current_date.year}-{current_date.month}: {exc}",
                exc_info=True,
            )
            if current_date.month == 12:
                current_date = datetime(current_date.year + 1, 1, 1, tzinfo=UTC)
            else:
                current_date = datetime(current_date.year, current_date.month + 1, 1, tzinfo=UTC)

    logger.info(f"Total events found: {len(events)}")
    return events


def process_mtgo_event(
    event_url: str,
    mtg_format: str = "modern",
    delay: float = MTGO_BACKGROUND_FETCH_DELAY_SECONDS,
):
    """
    Fetch and process a single MTGO event.

    Args:
        event_url: URL of the MTGO event
        mtg_format: Format for archetype classification (default: "modern")
        delay: Delay in seconds between requests (default: 2.0)
    """
    if _mtgo_feature_disabled("skipping process_mtgo_event"):
        return 0

    try:
        logger.info(f"Fetching MTGO event: {event_url}")

        payload = fetch_deck_event(event_url)
        event_date = payload.get("publish_date", datetime.now(UTC).isoformat()[:10])
        event_title = payload.get("title", "MTGO Event")

        raw_decklists = payload.get("decklists", [])
        if not raw_decklists:
            logger.warning(f"No decklists found in event {event_url}")
            return 0

        classifier = ArchetypeClassifier()
        deck_cache = get_deck_cache()

        clean_decks = [parse_mtgo_deck(raw_deck) for raw_deck in raw_decklists]
        classifier_decks = [convert_deck_to_classifier_format(deck) for deck in clean_decks]

        classifier.assign_archetypes(classifier_decks, mtg_format)

        cached_count = 0
        for idx, (clean_deck, classifier_deck) in enumerate(zip(clean_decks, classifier_decks), 1):
            deck_id = clean_deck["deck_id"]
            if not deck_id:
                logger.warning(f"Deck {idx} has no deck_id, skipping")
                continue

            deck_text = deck_to_text(clean_deck)
            success = deck_cache.set(deck_id, deck_text, source="mtgo")
            if success:
                cached_count += 1
            else:
                logger.warning(f"Failed to cache deck {deck_id}")
                continue

            archetype = classifier_deck.get("archetype", "Unknown")
            player = clean_deck.get("player", "Unknown")
            wins = clean_deck.get("wins", "5")
            losses = clean_deck.get("losses", "0")
            result = f"{wins}-{losses}"

            deck_metadata = {
                "number": deck_id,
                "date": event_date,
                "event": event_title,
                "result": result,
                "player": player,
                "archetype": archetype,
                "name": archetype,
                "source": "mtgo",
                "format": mtg_format,
            }

            try:
                save_mtgo_deck_metadata(archetype, mtg_format, deck_metadata)
            except Exception as meta_exc:
                logger.warning(f"Failed to save MTGO deck metadata for {deck_id}: {meta_exc}")

        logger.info(f"Cached {cached_count}/{len(clean_decks)} decks from {event_url}")

        # Polite delay between events
        time.sleep(delay)

        return cached_count

    except Exception as exc:
        logger.error(f"Failed to process MTGO event {event_url}: {exc}", exc_info=True)
        return 0


def fetch_mtgo_data_background(
    days: int = MTGO_BACKGROUND_FETCH_DAYS,
    mtg_format: str = "modern",
    delay: float = MTGO_BACKGROUND_FETCH_DELAY_SECONDS,
):
    """
    Background task to fetch MTGO data for the past N days.

    Args:
        days: Number of days to fetch (default: 7)
        mtg_format: Format to fetch (default: "modern")
        delay: Delay between requests in seconds (default: 2.0)

    Returns:
        Dict with stats about the fetch operation
    """
    if _mtgo_feature_disabled("skipping background fetch"):
        return {
            "events_found": 0,
            "events_processed": 0,
            "total_decks_cached": 0,
            "elapsed_seconds": 0,
        }

    logger.info(f"Starting MTGO background fetch for past {days} days")

    start_time = time.time()
    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)

    # Fetch event list
    events = fetch_mtgo_events_for_period(start_date, end_date, mtg_format)
    logger.info(f"Found {len(events)} MTGO events in the past {days} days")

    # Process each event
    total_decks = 0
    successful_events = 0

    for idx, event in enumerate(events, 1):
        logger.info(f"Processing event {idx}/{len(events)}: {event['title']}")

        decks_cached = process_mtgo_event(event["url"], mtg_format=mtg_format, delay=delay)

        if decks_cached > 0:
            successful_events += 1
            total_decks += decks_cached

    elapsed = time.time() - start_time

    stats = {
        "events_found": len(events),
        "events_processed": successful_events,
        "total_decks_cached": total_decks,
        "elapsed_seconds": elapsed,
    }

    logger.info(f"MTGO background fetch complete: {stats}")
    return stats
