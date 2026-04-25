import json
import re
import time
from datetime import datetime, timedelta
from urllib.parse import unquote

import bs4
from curl_cffi import requests
from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import (
    ARCHETYPE_CACHE_FILE,
    ARCHETYPE_DECKS_CACHE_FILE,
    ARCHETYPE_LIST_CACHE_FILE,
    CURR_DECK_FILE,
    DECK_TEXT_CACHE_FILE,
    GOLDFISH_DECK_TABLE_COL_DATE,
    GOLDFISH_DECK_TABLE_COL_EVENT,
    GOLDFISH_DECK_TABLE_COL_NUMBER,
    GOLDFISH_DECK_TABLE_COL_PLAYER,
    GOLDFISH_DECK_TABLE_COL_RESULT,
    METAGAME_CACHE_TTL_SECONDS,
    MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
    MTGGOLDFISH_STALE_CACHE_SECONDS,
    MTGGOLDFISH_STATS_LOOKBACK_DAYS,
    ONE_DAY_SECONDS,
)
from utils.deck_text_cache import get_deck_cache
from utils.json_io import fast_load


def _load_cached_archetypes(mtg_format: str, max_age: int = METAGAME_CACHE_TTL_SECONDS):
    if not ARCHETYPE_LIST_CACHE_FILE.exists():
        return None
    try:
        data = fast_load(ARCHETYPE_LIST_CACHE_FILE)
    except Exception as exc:
        logger.warning(f"Cached archetype list invalid: {exc}")
        return None
    entry = data.get(mtg_format)
    if not entry:
        return None
    if time.time() - entry.get("timestamp", 0) > max_age:
        return None
    return entry.get("items")


def _save_cached_archetypes(mtg_format: str, items: list[dict]):
    try:
        data = fast_load(ARCHETYPE_LIST_CACHE_FILE) if ARCHETYPE_LIST_CACHE_FILE.exists() else {}
    except Exception:
        data = {}
    data[mtg_format] = {"timestamp": time.time(), "items": items}
    ARCHETYPE_LIST_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ARCHETYPE_LIST_CACHE_FILE.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def get_archetypes(
    mtg_format: str, cache_ttl: int = METAGAME_CACHE_TTL_SECONDS, allow_stale: bool = True
):
    mtg_format = mtg_format.lower()
    cached = _load_cached_archetypes(mtg_format, cache_ttl)
    if cached is not None:
        logger.debug(f"Using cached archetypes for {mtg_format}")
        return cached

    logger.debug(f"Fetching archetypes for {mtg_format} from MTGGoldfish")
    try:
        page = requests.get(
            f"https://www.mtggoldfish.com/metagame/{mtg_format}/full",
            impersonate="chrome",
            timeout=MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
        )
        page.raise_for_status()
    except Exception as exc:
        logger.error(f"Failed to fetch archetype page: {exc}")
        if allow_stale:
            stale = _load_cached_archetypes(mtg_format, max_age=MTGGOLDFISH_STALE_CACHE_SECONDS)
            if stale is not None:
                logger.warning(f"Using stale archetype cache for {mtg_format}")
                return stale
        raise

    soup = bs4.BeautifulSoup(page.text, "lxml")
    metagame_decks = soup.select_one("#metagame-decks-container")
    if not metagame_decks:
        raise RuntimeError("Failed to locate metagame deck container")
    archetypes: list[bs4.Tag] = metagame_decks.find_all("span", attrs={"class": "deck-price-paper"})
    archetypes = [tag for tag in archetypes if tag.find("a") and not tag.find("div")]
    items = [
        {
            "name": tag.text.strip(),
            "href": tag.find("a")["href"].replace("/archetype/", "").replace("#paper", ""),
        }
        for tag in archetypes
    ]

    # Deduplicate by archetype name (MTGGoldfish sometimes returns duplicate names with different hrefs)
    # Keep first occurrence which typically has the cleaner/shorter href
    seen_names = set()
    unique_items = []
    for item in items:
        name_lower = item["name"].lower()
        if name_lower not in seen_names:
            seen_names.add(name_lower)
            unique_items.append(item)
        else:
            logger.debug(f"Skipping duplicate archetype: {item['name']} (href: {item['href']})")

    _save_cached_archetypes(mtg_format, unique_items)
    return unique_items


def _load_cached_archetype_decks(archetype: str, max_age: int = METAGAME_CACHE_TTL_SECONDS):
    if not ARCHETYPE_DECKS_CACHE_FILE.exists():
        return None
    with locked_path(ARCHETYPE_DECKS_CACHE_FILE):
        try:
            data = fast_load(ARCHETYPE_DECKS_CACHE_FILE)
        except Exception as exc:
            logger.warning(f"Cached archetype decks invalid: {exc}")
            return None
    entry = data.get(archetype)
    if not entry:
        return None
    if time.time() - entry.get("timestamp", 0) > max_age:
        return None
    return entry.get("items")


def _save_cached_archetype_decks(archetype: str, items: list[dict]):
    ARCHETYPE_DECKS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(ARCHETYPE_DECKS_CACHE_FILE):
        try:
            data = (
                fast_load(ARCHETYPE_DECKS_CACHE_FILE) if ARCHETYPE_DECKS_CACHE_FILE.exists() else {}
            )
        except Exception:
            data = {}
        data[archetype] = {"timestamp": time.time(), "items": items}
        atomic_write_json(ARCHETYPE_DECKS_CACHE_FILE, data, indent=2)


def get_archetype_decks(archetype: str):
    # Check cache first
    cached = _load_cached_archetype_decks(archetype)
    if cached is not None:
        logger.debug(f"Using cached decks for archetype {archetype}")
        return cached

    logger.debug(f"Fetching decks for archetype {archetype} from MTGGoldfish")
    try:
        page = requests.get(
            f"https://www.mtggoldfish.com/archetype/{archetype}/decks",
            impersonate="chrome",
            timeout=MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
        )
        page.raise_for_status()
    except Exception as exc:
        logger.error(f"Failed to fetch decks for archetype {archetype}: {exc}")
        return []

    soup = bs4.BeautifulSoup(page.text, "lxml")
    table = soup.select_one("table.table-striped")
    if not table:
        logger.warning(f"Deck table missing for archetype {archetype}")
        return []
    trs: list[bs4.Tag] = table.find_all("tr")
    trs = trs[1:]
    decks = []
    for tr in trs:
        tds: list[bs4.Tag] = tr.find_all("td")
        decks.append(
            {
                "date": tds[GOLDFISH_DECK_TABLE_COL_DATE].text.strip(),
                "number": tds[GOLDFISH_DECK_TABLE_COL_NUMBER]
                .select_one("a")
                .attrs.get("href")
                .replace("/deck/", ""),
                "player": tds[GOLDFISH_DECK_TABLE_COL_PLAYER].text.strip(),
                "event": tds[GOLDFISH_DECK_TABLE_COL_EVENT].text.strip(),
                "result": tds[GOLDFISH_DECK_TABLE_COL_RESULT].text.strip(),
                "name": archetype,
                "source": "mtggoldfish",
            }
        )
    # Save to cache
    _save_cached_archetype_decks(archetype, decks)
    return decks


def get_archetype_stats(mtg_format: str):
    cache_path = ARCHETYPE_CACHE_FILE
    stats = {}
    if cache_path.exists():
        try:
            stats = fast_load(cache_path)
        except Exception as exc:
            logger.warning(f"Invalid archetype cache at {cache_path}: {exc}")
            stats = {}
        if (
            mtg_format in stats
            and time.time() - stats[mtg_format].get("timestamp", 0) < ONE_DAY_SECONDS
        ):
            return stats
    archetypes = get_archetypes(mtg_format)
    stats = {mtg_format: {"timestamp": time.time()}}
    for archetype in archetypes:
        stats[mtg_format][archetype["name"]] = {"decks": get_archetype_decks(archetype["href"])}
        # for day in the past week display the number of decks
        stats[mtg_format][archetype["name"]]["results"] = {}
        for day in range(MTGGOLDFISH_STATS_LOOKBACK_DAYS):
            date = (datetime.now() - timedelta(days=day)).strftime("%Y-%m-%d")
            stats[mtg_format][archetype["name"]]["results"][date] = len(
                [
                    deck
                    for deck in stats[mtg_format][archetype["name"]]["decks"]
                    if date.lower() in deck["date"].lower()
                ]
            )
    ARCHETYPE_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with ARCHETYPE_CACHE_FILE.open("w", encoding="utf-8") as f:
        json.dump(stats, f, indent=4)
    return stats


# Flag to track if migration has been attempted
_migration_attempted = False


def _ensure_cache_migration():
    """Migrate old JSON cache to SQLite on first use."""
    global _migration_attempted
    if _migration_attempted:
        return

    _migration_attempted = True
    cache = get_deck_cache()

    # Try to migrate from old JSON cache
    if DECK_TEXT_CACHE_FILE.exists():
        logger.info("Found existing JSON deck cache, migrating to SQLite...")
        migrated = cache.migrate_from_json(DECK_TEXT_CACHE_FILE)

        if migrated > 0:
            # Backup old JSON cache and remove it
            backup_path = DECK_TEXT_CACHE_FILE.with_suffix(".json.backup")
            try:
                DECK_TEXT_CACHE_FILE.rename(backup_path)
                logger.info(f"Migrated {migrated} decks, backed up JSON cache to {backup_path}")
            except OSError as exc:
                logger.warning(f"Could not backup old JSON cache: {exc}")


def fetch_deck_text(deck_num: str, source_filter: str | None = None) -> str:
    """
    Return a deck list as text, using the SQLite cache when available.

    This function now uses a high-performance SQLite backend that scales
    to millions of cached decks without performance degradation.

    Args:
        deck_num: MTGGoldfish deck number
        source_filter: Optional source filter ('mtggoldfish', 'mtgo', or None for both)

    Returns:
        Deck text content

    Raises:
        ValueError: If deck cannot be parsed from MTGGoldfish
    """
    # Ensure migration on first use
    _ensure_cache_migration()

    # Get SQLite cache instance
    cache = get_deck_cache()

    # Check cache first, applying source filter
    # source_filter="both" means None (any source), otherwise use specific source
    cache_source = None if source_filter == "both" else source_filter
    cached_text = cache.get(deck_num, source=cache_source)
    if cached_text is not None:
        return cached_text

    # Cache miss - only download from MTGGoldfish if source allows it
    if source_filter == "mtgo":
        logger.warning(
            f"Deck {deck_num} not found in MTGO cache and source filter blocks MTGGoldfish"
        )
        raise ValueError(f"Deck {deck_num} not available from MTGO source")

    # Download from MTGGoldfish. The /deck/{id} endpoint went behind Cloudflare's
    # managed challenge, which rejects every plain-HTTP client (and headless Chrome).
    # If it doesn't return parseable HTML, fall back to /deck/visual/{id}, which
    # is served unprotected.
    logger.info(f"Downloading deck {deck_num} from MTGGoldfish")
    deck_text: str | None = None
    try:
        page = requests.get(f"https://www.mtggoldfish.com/deck/{deck_num}", impersonate="chrome")
        page.raise_for_status()
        match = re.search(r'initializeDeckComponents\([^,]+,\s*[^,]+,\s*"([^"]+)"', page.text)
        if match:
            deck_text = unquote(match.group(1))
        else:
            logger.warning(
                f"Deck {deck_num} HTTP response missing deck payload "
                "(likely Cloudflare challenge); attempting visual-page fallback"
            )
    except Exception as exc:
        logger.warning(
            f"MTGGoldfish HTTP fetch failed for deck {deck_num}: {exc}; "
            "attempting visual-page fallback"
        )

    if deck_text is None:
        try:
            from navigators.mtggoldfish_visual import fetch_deck_text_from_visual_page

            deck_text = fetch_deck_text_from_visual_page(deck_num)
        except Exception as exc:
            logger.error(f"Visual-page fallback failed for deck {deck_num}: {exc}")
            raise ValueError(f"Could not parse deck data for deck {deck_num}") from exc

    # Store in cache with mtggoldfish source
    cache.set(deck_num, deck_text, source="mtggoldfish")

    return deck_text


def download_deck(deck_num: str, source_filter: str | None = None):
    """
    Downloads a deck list and writes it to CURR_DECK_FILE while maintaining cache compatibility.

    Args:
        deck_num: MTGGoldfish deck number
        source_filter: Optional source filter ('mtggoldfish', 'mtgo', or 'both')
    """
    deck_text = fetch_deck_text(deck_num, source_filter=source_filter)

    CURR_DECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with CURR_DECK_FILE.open("w", encoding="utf-8") as f:
        f.write(deck_text)


if __name__ == "__main__":
    stats = get_archetype_stats("modern")
    print(
        json.dumps(
            {s: stats["modern"][s]["results"] for s in stats["modern"] if "timestamp" not in s},
            indent=8,
        )
    )
    print("done")
