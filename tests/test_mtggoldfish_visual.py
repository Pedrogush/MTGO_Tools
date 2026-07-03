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

from unittest.mock import Mock, patch

import pytest

from repositories.scrapers.mtggoldfish_visual import (
    fetch_deck_text_from_visual_page,
    parse_visual_page,
)
from utils.constants.timing import MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS

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


def test_parse_visual_page_sideboard_only_keeps_leading_separator():
    # Empty mainboard pile + populated sideboard: the formatter still joins on
    # the blank-line separator, so the output begins with "\n\n".
    html = _visual_html(main_alts=[], side_alts=["Galvanic Blast", "Galvanic Blast"])

    text = parse_visual_page(html)

    assert text == "\n\n2 Galvanic Blast"
    main_block, sep, side_block = text.partition("\n\n")
    assert main_block == ""
    assert sep == "\n\n"
    assert side_block == "2 Galvanic Blast"


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


@patch("repositories.scrapers.mtggoldfish_visual.requests.get")
def test_fetch_deck_text_from_visual_page_offline(mock_get):
    """Offline cover of the fetch path: mock the HTTP call, parse fixed HTML."""
    html = _visual_html(
        main_alts=["Mox Opal", "Mox Opal", "Ornithopter"],
        side_alts=["Galvanic Blast", "Galvanic Blast"],
    )
    mock_response = Mock()
    mock_response.text = html
    mock_response.raise_for_status = Mock()
    mock_get.return_value = mock_response

    text = fetch_deck_text_from_visual_page("12345")

    # The fetcher hits the unprotected visual endpoint for the given deck id.
    mock_get.assert_called_once()
    assert mock_get.call_args.args[0] == "https://www.mtggoldfish.com/deck/visual/12345"
    # impersonate="chrome" is load-bearing: it is what bypasses Cloudflare on the
    # live endpoint, so dropping it must fail this test rather than only break
    # in production. The request timeout is pinned to the shared constant.
    assert mock_get.call_args.kwargs["impersonate"] == "chrome"
    assert mock_get.call_args.kwargs["timeout"] == MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS
    # raise_for_status must be honoured before parsing.
    mock_response.raise_for_status.assert_called_once()
    # The page text is parsed into the same plain-text decklist contract.
    main_block, sep, side_block = text.partition("\n\n")
    assert sep == "\n\n"
    assert main_block == "2 Mox Opal\n1 Ornithopter"
    assert side_block == "2 Galvanic Blast"


@patch("repositories.scrapers.mtggoldfish_visual.requests.get")
def test_fetch_deck_text_from_visual_page_propagates_http_error(mock_get):
    """A non-2xx response surfaces via raise_for_status, not silent parsing."""
    mock_response = Mock()
    mock_response.raise_for_status = Mock(side_effect=RuntimeError("404"))
    mock_get.return_value = mock_response

    with pytest.raises(RuntimeError):
        fetch_deck_text_from_visual_page("12345")


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
