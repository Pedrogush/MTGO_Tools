"""Tests for repositories/scrapers/mtggoldfish_visual.py.

Two layers of coverage:

* Offline unit tests feed fixed ``/deck/visual/`` HTML straight to
  :func:`parse_visual_page` so the deterministic parsing contract (alt-text
  counting, sideboard formatting, the empty-page error path) is verified on
  every CI run, independent of MTGGoldfish availability.
* A network-gated smoke test still hits the real ``/deck/visual/`` endpoint —
  the whole point of the fallback is to exercise an unprotected URL — to catch
  upstream page-structure changes.
"""

import pytest

from repositories.scrapers.mtggoldfish_visual import (
    fetch_deck_text_from_visual_page,
    parse_visual_page,
)

# Modern Affinity decklist sourced from a real MTGO Challenge result. Picked
# because it exercises both mainboard and sideboard parsing.
LIVE_DECK_NUM = "7750657"


def _pile(selector_class: str, alts: list[str]) -> str:
    """Render a ``.deck-visual-playmat-*`` container with one card img per alt."""
    imgs = "".join(f'<img class="deck-visual-pile-card" alt="{alt}">' for alt in alts)
    return f'<div class="{selector_class}">{imgs}</div>'


def _visual_html(main_alts: list[str], side_alts: list[str] | None = None) -> str:
    main = _pile("deck-visual-playmat-maindeck", main_alts)
    side = _pile("deck-visual-playmat-sideboard", side_alts) if side_alts is not None else ""
    return f"<html><body>{main}{side}</body></html>"


def test_parse_visual_page_counts_alt_text_with_sideboard():
    html = _visual_html(
        main_alts=["Mox Opal", "Mox Opal", "Ornithopter"],
        side_alts=["Galvanic Blast", "Galvanic Blast"],
    )

    text = parse_visual_page(html)

    main_block, sep, side_block = text.partition("\n\n")
    assert sep == "\n\n"
    # Insertion order is preserved; duplicate alts are tallied.
    assert main_block == "2 Mox Opal\n1 Ornithopter"
    assert side_block == "2 Galvanic Blast"


def test_parse_visual_page_mainboard_only_has_no_separator():
    html = _visual_html(main_alts=["Mox Opal", "Ornithopter"])

    text = parse_visual_page(html)

    assert text == "1 Mox Opal\n1 Ornithopter"
    assert "\n\n" not in text


def test_parse_visual_page_skips_blank_alt_text():
    html = _visual_html(main_alts=["Mox Opal", "", "   ", "Ornithopter"])

    text = parse_visual_page(html)

    assert text == "1 Mox Opal\n1 Ornithopter"


def test_parse_visual_page_raises_when_no_card_piles():
    # Containers present but empty -> no cards counted -> explicit error.
    html = _visual_html(main_alts=[], side_alts=[])

    with pytest.raises(ValueError):
        parse_visual_page(html)


def test_parse_visual_page_raises_when_containers_missing():
    with pytest.raises(ValueError):
        parse_visual_page("<html><body><p>no piles here</p></body></html>")


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
