"""Pure-data helpers, legacy-path constants, and i18n helper for the opponent tracker.

Module-level constants ``LEGACY_DECK_MONITOR_CONFIG``, ``LEGACY_DECK_MONITOR_CACHE``,
and ``LEGACY_DECK_MONITOR_CACHE_CONFIG`` live here because they are read-only
filesystem paths consumed by the cache/config loaders.  They are re-exported from
the package's ``__init__.py`` so external callers (notably the UI test harness in
``tests/ui/conftest.py``) can continue to
``monkeypatch.setattr(identify_opponent, "LEGACY_DECK_MONITOR_CONFIG", ...)``.

``get_latest_deck`` is a read-only web scraping helper that queries MTGGoldfish;
it is kept at module scope (not on the frame class) because it has no instance
state and is invoked from the background poll worker.
"""

from __future__ import annotations

from pathlib import Path

import bs4
from curl_cffi import requests
from loguru import logger

from utils.constants import (
    CONFIG_DIR,
    GOLDFISH,
    GOLDFISH_PLAYER_TABLE_COLUMNS,
    MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
)
from utils.i18n import translate

LEGACY_DECK_MONITOR_CONFIG = Path("deck_monitor_config.json")
LEGACY_DECK_MONITOR_CACHE = Path("deck_monitor_cache.json")
LEGACY_DECK_MONITOR_CACHE_CONFIG = CONFIG_DIR / "deck_monitor_cache.json"


def get_latest_deck(player: str, option: str):
    """
    Web scraping function: queries MTGGoldfish for a player's recent tournament results.
    Returns the most recent deck archetype the player used in the specified format.
    This is read-only web scraping and does not interact with MTGO client.
    """
    if not player:
        return "No player name"
    logger.debug(player)
    player = player.strip()
    try:
        res = requests.get(
            GOLDFISH + player,
            impersonate="chrome",
            timeout=MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
    except Exception as exc:
        logger.error(f"Failed to fetch player page for {player}: {exc}")
        return "Unknown"
    soup = bs4.BeautifulSoup(res.text, "lxml")
    table = soup.find("table")
    if not table and player[0] == "0":
        logger.debug("ocr possibly mistook the letter O for a zero")
        player = "O" + player[1:]
        logger.debug(player)
        try:
            res = requests.get(
                GOLDFISH + player,
                impersonate="chrome",
                timeout=MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
            )
            res.raise_for_status()
        except Exception as exc:
            logger.error(f"Failed retry fetch for player {player}: {exc}")
            return "Unknown"
        soup = bs4.BeautifulSoup(res.text, "lxml")
        table = soup.find("table")
    if not table:
        logger.debug(f"No results table found for player {player}")
        return "Unknown"
    entries = table.find_all("tr")
    for entry in entries:
        tds = entry.find_all("td")
        if not tds:
            continue
        if len(tds) != GOLDFISH_PLAYER_TABLE_COLUMNS:
            continue
        entry_format: str = tds[2].text
        if entry_format.lower().strip() == option.lower():
            logger.debug(f"{player} last 5-0 seen playing {tds[3].text}, in {tds[0].text}")
            return tds[3].text

    return "Unknown"


class MTGOpponentDeckSpyPropertiesMixin:
    """Translation helper and pure predicates for :class:`MTGOpponentDeckSpy`.

    Kept as a mixin (no ``__init__``) so the main class remains the single
    source of truth for instance-state initialization.
    """

    _locale: str | None

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _is_widget_ok(self, widget) -> bool:
        if widget is None:
            return False
        try:
            # Try to access a basic property to verify widget is still valid
            _ = widget.GetId()
            return True
        except (RuntimeError, AttributeError):
            return False
