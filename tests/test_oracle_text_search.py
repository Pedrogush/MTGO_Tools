"""Matching rules behind the deck builder's oracle ``Text`` filter (issue #1032).

The end-to-end behaviour -- typing into the real box, picking ``=``/``≈`` and
reading the rows the panel shows -- is covered in
``tests/ui/test_builder_oracle_text_search.py``. These pin the rules underneath
it without a wx App.
"""

from __future__ import annotations

import pytest

from services.search_service.oracle_text import (
    TEXT_MODE_EXACT,
    TEXT_MODE_WORDS,
    card_oracle_text,
    matches_oracle_text,
    stem_word,
)


def _matches(text: str, query: str, mode: str) -> bool:
    return matches_oracle_text(card_oracle_text({"oracle_text": text}), query, mode)


@pytest.mark.parametrize(
    ("word", "stem"),
    [
        ("gains", "gain"),
        ("gained", "gain"),
        ("loses", "los"),
        ("abilities", "abilit"),
        ("library", "librar"),
        ("untapped", "untap"),
        ("flying", "fly"),
        ("prowess", "prowess"),
        ("reach", "reach"),
        ("dies", "die"),
        ("any", "any"),
        ("the", "the"),
    ],
)
def test_stem_word_is_a_prefix_shared_by_inflections(word, stem):
    assert stem_word(word) == stem
    assert word.startswith(stem)


@pytest.mark.parametrize("mode", [TEXT_MODE_EXACT, TEXT_MODE_WORDS])
@pytest.mark.parametrize(
    "text",
    [
        "Hexproof (This creature can't be the target of spells or abilities your opponents "
        "control.)",
        "Flying, hexproof",
        "Hexproof from blue",
        "Enchanted creature has HEXPROOF.",
    ],
)
def test_keyword_is_found_in_either_mode(text, mode):
    assert _matches(text, "hexproof", mode)
    assert _matches(text, "Hexproof", mode)


def test_back_face_text_is_searched():
    card = {
        "oracle_text": "At the beginning of your upkeep, transform this creature.",
        "back_oracle_text": "Flying",
    }
    text = card_oracle_text(card)
    assert matches_oracle_text(text, "flying", TEXT_MODE_EXACT)
    assert matches_oracle_text(text, "flying", TEXT_MODE_WORDS)


def test_exact_mode_needs_the_phrase_verbatim():
    assert _matches("Target creature gains indestructible.", "gains indestructible", "all")
    assert not _matches("Creatures gain indestructible.", "gains indestructible", "all")
    assert not _matches("Indestructible. It gains flying.", "gains indestructible", "all")


def test_exact_mode_anchors_the_phrase_to_a_word_start():
    # "=" used to find "reach" inside "Treacherous", so Treacherous Terrain was
    # the one card "=" returned for reach that "≈" did not (697 against 696).
    text = "Treacherous Terrain deals damage to each opponent equal to the number of lands."
    assert not _matches(text, "reach", "all")
    assert not _matches("Breach the wall.", "reach", "all")
    # Only the start is anchored: the phrase may run on into a longer word.
    assert _matches("Up to two target creatures gain flying.", "target creature", "all")
    assert _matches("{T}: Add {G}.", "{t}: add", "all")


def test_exact_mode_ignores_repeated_spaces_in_the_query():
    assert _matches("Search your library for a card.", "search  your   library", "all")


def test_words_mode_matches_inflections_in_any_order():
    assert _matches("Indestructible. It gains flying.", "gains indestructible", "any")
    assert _matches("Permanents you control gain indestructible.", "gains indestructible", "any")
    assert _matches("Lands lose all land types and abilities.", "loses all abilities", "any")


def test_words_mode_anchors_words_to_word_starts():
    # "reach" inside "breach" is not the word reach; "end" inside "spend" is not "end".
    assert not _matches("Breach the wall.", "reach", "any")
    assert not _matches(
        "Spend mana as though it were any color of turn.", "until end of turn", "any"
    )


def test_words_mode_needs_every_word():
    assert not _matches("Target player draws a card.", "target creature", "any")


def test_words_mode_keeps_symbol_terms_as_substrings():
    assert _matches("{T}: Add {G}.", "{t}: add", "any")
    assert _matches("Put a +1/+1 counter on it.", "+1/+1 counter", "any")


def test_empty_query_matches_everything():
    assert _matches("Flying", "   ", "any")
    assert _matches("Flying", "", "all")
