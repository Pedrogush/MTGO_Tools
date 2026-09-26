"""The deck's name: what it is called, and which file it is written to.

The name used to decide the deck's history as well -- it was the key the
per-deck git repo was found by -- which meant renaming a deck emptied its
version graph. The history is keyed by the deck's stable id now
(:mod:`services.deck_identity`), and the name is a label again.

Three rules the rest of the app relies on:

**Empty means unset, and only empty.** A deck with no name holds ``""``. The
"no name yet" wording belongs to the UI and is never written here and never
persisted -- it is display text, not something a deck is called.

**A name is always a legal file stem.** :func:`set_deck_name` sanitizes on the
way in, so callers never have to. What comes back out is exactly what will be
written to disk, which is what the UI shows.

**Renaming writes a new file, and never moves the old one.** The name decides
the file, so a new name points the next save at a new file; the old one is left
exactly where it is. Both are the same deck, and both are covered by the one
history its id keys.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from utils.deck import sanitize_filename

#: Where the chosen name lives on a deck record. Deliberately *not* ``name``,
#: which already holds the source's own label -- an archetype slug like
#: ``modern-affinity`` for a scraped list. Conflating the two is what made the
#: second save of a deck offer a different file from the first.
DECK_NAME_KEY = "deck_name"

#: What a name sanitizes to when nothing usable survives.
NAME_FALLBACK = "saved_deck"


def deck_name_of(deck: dict[str, Any] | None) -> str:
    """The deck's chosen name, or ``""`` when it has none yet."""
    if not deck:
        return ""
    return str(deck.get(DECK_NAME_KEY) or "").strip()


def has_deck_name(deck: dict[str, Any] | None) -> bool:
    """Whether the user has named this deck."""
    return bool(deck_name_of(deck))


def clean_deck_name(name: str | None) -> str:
    """``name`` as it will actually be stored and written to disk.

    Returns ``""`` for anything that cannot become a file stem, so a caller can
    treat "rejected" and "unset" as the same condition.
    """
    text = str(name or "").strip()
    if not text:
        return ""
    return sanitize_filename(text, fallback=NAME_FALLBACK)


def set_deck_name(deck: dict[str, Any] | None, name: str | None) -> str:
    """Name ``deck``, returning the name as stored (``""`` when rejected).

    An empty or unusable name is refused rather than stored: the placeholder
    the UI shows for an unnamed deck is display text, not a name, and storing
    it would key every unnamed deck to one shared history.
    """
    if deck is None:
        return ""
    cleaned = clean_deck_name(name)
    if not cleaned:
        return ""
    deck[DECK_NAME_KEY] = cleaned
    return cleaned


def adopt_file_name(deck: dict[str, Any] | None, file_path: Path | str | None) -> str:
    """Give an unnamed deck the name of the file it came from.

    A deck opened from disk is called what its file is called, which is what the
    user already believes. It is also what a history written before decks had
    ids is filed under, so this is what lets such a deck find that history and
    take it over on its next save. Never overwrites a name the user chose.
    """
    if deck is None or file_path is None or has_deck_name(deck):
        return deck_name_of(deck)
    return set_deck_name(deck, Path(file_path).stem)


def deck_file_for(deck: dict[str, Any] | None, save_dir: Path) -> Path | None:
    """The file a save of ``deck`` should write, or ``None`` while unnamed.

    A deck whose existing file already matches its name keeps that file,
    wherever on disk it happens to live -- a list opened from somewhere other
    than the deck folder goes on saving where it was opened from. Once the name
    and the file disagree the name wins, which is what makes a rename write a
    new file instead of overwriting the old one.
    """
    name = deck_name_of(deck)
    if not name:
        return None
    existing = (deck or {}).get("path")
    if existing:
        current = Path(str(existing))
        if current.stem.lower() == name.lower():
            return current
    return Path(save_dir) / f"{name}.txt"


__all__ = [
    "DECK_NAME_KEY",
    "NAME_FALLBACK",
    "adopt_file_name",
    "clean_deck_name",
    "deck_file_for",
    "deck_name_of",
    "has_deck_name",
    "set_deck_name",
]
