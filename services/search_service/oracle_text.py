"""Oracle-text query matching for the deck builder's ``Text`` filter.

The filter has two modes, picked by the ``=`` / ``≈`` choice next to the box:

``"all"`` (``=``, exact)
    The query, with its whitespace collapsed, must appear verbatim in the
    card's oracle text, starting where a word starts: ``gains
    indestructible`` matches "…gains indestructible until end of turn" and
    nothing that merely mentions both words, and ``reach`` does not match
    "Treacherous Terrain".

``"any"`` (``≈``, words)
    Every word of the query must start a word somewhere in the oracle text, in
    any order. Each word is first cut back to a crude stem, so ``gains`` also
    finds "gain" and "gained", ``loses`` finds "lose" and "lost", and
    ``abilities`` finds "ability". A stem is always a prefix of the word typed,
    so a card that contains the typed word itself is never lost to stemming.

Both modes are case-insensitive and read the back face of a double-faced card
as well as its front, so Delver of Secrets turns up for ``flying``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from functools import lru_cache
from typing import Any

TEXT_MODE_EXACT = "all"
TEXT_MODE_WORDS = "any"

_MIN_STEM = 3
# Tried in order; the first suffix whose removal leaves a long enough stem wins.
_SUFFIXES = ("ies", "ing", "ed", "es", "s", "e", "y")
_WORD_CHARS = "a-z0-9"


def card_oracle_text(card: Mapping[str, Any] | Any) -> str:
    """Front and back oracle text of ``card``, lowercased and newline-joined."""
    front = card.get("oracle_text") or card.get("text") or ""
    back = card.get("back_oracle_text") or ""
    return _normalize(f"{front}\n{back}" if back else front)


def matches_oracle_text(text: str, query: str, mode: str = TEXT_MODE_EXACT) -> bool:
    """Whether already-normalized ``text`` satisfies ``query`` in ``mode``."""
    return _compile_query(query, mode)(text)


def stem_word(word: str) -> str:
    """Cut an alphabetic ``word`` back to a prefix shared by its inflections."""
    for suffix in _SUFFIXES:
        if suffix == "s" and word.endswith("ss"):
            continue
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM:
            stem = word[: -len(suffix)]
            # tapped -> tapp -> tap, so "untapped" still finds "untap".
            if suffix in ("ed", "ing") and len(stem) > _MIN_STEM and stem[-1] == stem[-2]:
                stem = stem[:-1]
            return stem
    return word


def _normalize(text: str) -> str:
    return text.lower().replace("’", "'")


@lru_cache(maxsize=64)
def _compile_query(query: str, mode: str) -> Callable[[str], bool]:
    words = _normalize(query).split()
    if not words:
        return lambda _text: True
    if mode != TEXT_MODE_WORDS:
        phrase = re.compile(_word_start_pattern(" ".join(words)))
        return lambda text: phrase.search(text) is not None
    patterns = [re.compile(_word_pattern(word)) for word in words]
    return lambda text: all(pattern.search(text) for pattern in patterns)


def _word_pattern(word: str) -> str:
    if word.isalpha():
        word = stem_word(word)
    return _word_start_pattern(word)


def _word_start_pattern(term: str) -> str:
    escaped = re.escape(term)
    # Anchor to the start of a word only when the term itself starts with one;
    # "{t}:" or "+1/+1" have no word boundary in front of them to anchor to.
    if term[0].isalnum():
        return rf"(?<![{_WORD_CHARS}]){escaped}"
    return escaped


__all__ = [
    "TEXT_MODE_EXACT",
    "TEXT_MODE_WORDS",
    "card_oracle_text",
    "matches_oracle_text",
    "stem_word",
]
