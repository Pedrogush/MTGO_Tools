"""Integration test for navigators/mtggoldfish_visual.py against live MTGGoldfish.

This intentionally hits the real /deck/visual/ endpoint — the whole point of
the fallback is to exercise an unprotected URL, so mocking it would tell us
nothing about whether it still works.
"""

import pytest

from navigators.mtggoldfish_visual import fetch_deck_text_from_visual_page

# Modern Affinity decklist sourced from a real MTGO Challenge result. Picked
# because it exercises both mainboard and sideboard parsing.
LIVE_DECK_NUM = "7750657"


@pytest.mark.network
def test_fetch_deck_text_from_visual_page_returns_full_decklist():
    text = fetch_deck_text_from_visual_page(LIVE_DECK_NUM)

    main_block, _, side_block = text.partition("\n\n")
    main_lines = [ln for ln in main_block.splitlines() if ln.strip()]
    side_lines = [ln for ln in side_block.splitlines() if ln.strip()]

    main_count = sum(int(ln.split(maxsplit=1)[0]) for ln in main_lines)
    side_count = sum(int(ln.split(maxsplit=1)[0]) for ln in side_lines)

    # Modern decks: 60 mainboard, 15 sideboard.
    assert main_count == 60, f"expected 60 mainboard cards, got {main_count}\n{text}"
    assert side_count == 15, f"expected 15 sideboard cards, got {side_count}\n{text}"

    # Sanity: the deck should contain at least one signature Affinity card.
    assert "Mox Opal" in text
