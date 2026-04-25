"""Fallback deck fetcher that scrapes the MTGGoldfish ``/deck/visual/`` page.

The standard ``/deck/{id}`` endpoint is now behind Cloudflare's *managed*
challenge, which rejects every headless browser and every plain-HTTP client we
could try. The public ``/deck/visual/{id}`` view, however, is served without the
challenge and embeds one ``<img class="deck-visual-pile-card" alt="...">`` per
card copy inside ``.deck-visual-playmat-maindeck`` and
``.deck-visual-playmat-sideboard`` containers. Counting those by alt text
reconstructs the same plain-text deck list the primary scraper produces.
"""

from __future__ import annotations

from collections import OrderedDict

import bs4
from curl_cffi import requests
from loguru import logger

from utils.constants.timing import MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS

_MAIN_SELECTOR = ".deck-visual-playmat-maindeck"
_SIDE_SELECTOR = ".deck-visual-playmat-sideboard"
_CARD_IMG_SELECTOR = "img.deck-visual-pile-card"


def _count_cards(section: bs4.Tag | None) -> OrderedDict[str, int]:
    counts: OrderedDict[str, int] = OrderedDict()
    if section is None:
        return counts
    for img in section.select(_CARD_IMG_SELECTOR):
        name = (img.get("alt") or "").strip()
        if not name:
            continue
        counts[name] = counts.get(name, 0) + 1
    return counts


def _format_deck_text(
    mainboard: OrderedDict[str, int], sideboard: OrderedDict[str, int]
) -> str:
    main_text = "\n".join(f"{c} {n}" for n, c in mainboard.items())
    if not sideboard:
        return main_text
    side_text = "\n".join(f"{c} {n}" for n, c in sideboard.items())
    return f"{main_text}\n\n{side_text}"


def parse_visual_page(html: str) -> str:
    """Extract a plain-text decklist from rendered ``/deck/visual/`` HTML."""
    soup = bs4.BeautifulSoup(html, "lxml")
    mainboard = _count_cards(soup.select_one(_MAIN_SELECTOR))
    sideboard = _count_cards(soup.select_one(_SIDE_SELECTOR))
    if not mainboard and not sideboard:
        raise ValueError("Visual deck page contained no card piles")
    return _format_deck_text(mainboard, sideboard)


def fetch_deck_text_from_visual_page(deck_num: str) -> str:
    """Fallback fetcher: pull the deck text from the unprotected visual view."""
    url = f"https://www.mtggoldfish.com/deck/visual/{deck_num}"
    logger.info(f"Fetching deck {deck_num} from MTGGoldfish visual fallback")
    page = requests.get(
        url, impersonate="chrome", timeout=MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS
    )
    page.raise_for_status()
    return parse_visual_page(page.text)
