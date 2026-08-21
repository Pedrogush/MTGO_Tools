"""Accent-insensitive card-name keys.

MTGO writes card names in plain ASCII — ``Dain, Lord of the Iron Hills``,
``Anduril, Narsil Reforged`` — while Scryfall (and MTGJSON) carry the
typographically correct name, ``Dáin, Lord of the Iron Hills``. Every index in
the app is keyed by ``name.lower()``, so a deck loaded from MTGO misses on
every card whose real name has a diacritic: the local image index misses, the
Scryfall lookup *does* resolve (their name matching folds accents) but comes
back under the accented name, the match fails, and the download is reported as
a permanent "404 not found" (issue: LOTR cards never get images).

:func:`fold_card_name` produces the key both spellings share, so indexes can
carry a folded alias next to the exact key and lookups can fall back to it.
Folding is deliberately conservative: it only removes information that Scryfall
itself ignores when matching a name.
"""

from __future__ import annotations

import unicodedata

# Characters that NFKD leaves alone because they are distinct letters rather
# than letter+combining-mark pairs. Scryfall spells these out in ASCII (their
# "Aether Vial" was once "Æther Vial"), so fold them the same way.
_LETTER_FOLDS = str.maketrans(
    {
        "æ": "ae",
        "œ": "oe",
        "ø": "o",
        "đ": "d",
        "ð": "d",
        "ł": "l",
        "þ": "th",
        "ß": "ss",
    }
)

# Typographic punctuation MTGO and Scryfall disagree on.
_PUNCTUATION_FOLDS = str.maketrans(
    {
        "‘": "'",  # ‘
        "’": "'",  # ’
        "“": '"',  # “
        "”": '"',  # ”
        "‐": "-",  # ‐
        "‑": "-",  # ‑
        "‒": "-",  # ‒
        "–": "-",  # –
        "—": "-",  # —
        "−": "-",  # −
    }
)


def strip_accents(text: str) -> str:
    """Return *text* lowercased with combining diacritical marks removed (ó → o)."""
    lowered = (text or "").lower().translate(_LETTER_FOLDS)
    return "".join(
        char for char in unicodedata.normalize("NFKD", lowered) if not unicodedata.combining(char)
    )


def fold_card_name(name: str) -> str:
    """Return the lookup key shared by every spelling of *name*.

    Lowercased, accent-free, typographic punctuation normalized to ASCII and
    runs of whitespace collapsed. Returns ``""`` for empty/None input, which
    callers should treat as "no key" rather than as a real index entry.
    """
    folded = strip_accents(name).translate(_PUNCTUATION_FOLDS)
    return " ".join(folded.split())


__all__ = ["fold_card_name", "strip_accents"]
