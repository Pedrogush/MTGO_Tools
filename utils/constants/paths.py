"""Filesystem paths and config/cache locations."""

import sys
from pathlib import Path


def _default_base_dir() -> Path:
    """Return the writable base directory for config/cache/logging."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DATA_DIR = _default_base_dir()
CONFIG_DIR = BASE_DATA_DIR / "config"
CACHE_DIR = BASE_DATA_DIR / "cache"
DECKS_DIR = BASE_DATA_DIR / "decks"
DECK_SAVE_DIR = DECKS_DIR
LOGS_DIR = BASE_DATA_DIR / "logs"
CARD_DATA_DIR = BASE_DATA_DIR / "data"


def ensure_base_dirs() -> None:
    """Ensure base config/cache/deck/log directories exist without importing side effects."""
    BASE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for path in (CONFIG_DIR, CACHE_DIR, DECKS_DIR, LOGS_DIR, CARD_DATA_DIR):
        path.mkdir(parents=True, exist_ok=True)


CONFIG_FILE = CONFIG_DIR / "config.json"
DECK_MONITOR_CONFIG_FILE = CONFIG_DIR / "deck_monitor_config.json"
DECK_SELECTOR_SETTINGS_FILE = CONFIG_DIR / "deck_selector_settings.json"
LEADERBOARD_POSITIONS_FILE = CONFIG_DIR / "leaderboard_positions.json"

DECK_MONITOR_CACHE_FILE = CACHE_DIR / "deck_monitor_cache.json"
ARCHETYPE_CACHE_FILE = CACHE_DIR / "archetype_cache.json"
ARCHETYPE_LIST_CACHE_FILE = CACHE_DIR / "archetype_list.json"
MTGO_ARTICLES_CACHE_FILE = CACHE_DIR / "mtgo_articles.json"
MTGO_DECK_CACHE_FILE = CACHE_DIR / "mtgo_decks.json"
MTGO_METADATA_CACHE_FILE = CACHE_DIR / "mtgo_deck_metadata.json"
DECK_CACHE_DB_FILE = CACHE_DIR / "deck_cache.db"
DECK_TEXT_CACHE_FILE = CACHE_DIR / "deck_text_cache.json"  # Individual deck content
ARCHETYPE_DECKS_CACHE_FILE = CACHE_DIR / "archetype_decks_cache.json"  # Deck lists per archetype
DECK_CACHE_FILE = DECK_TEXT_CACHE_FILE
CURR_DECK_FILE = DECKS_DIR / "curr_deck.txt"
