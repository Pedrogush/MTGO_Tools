"""The deck's name: the one piece of state that decides its file and its history.

A deck's version history is keyed by the stem of the file behind it
(:func:`services.deck_vcs_service.deck_key_for`), so whatever picks that stem
decides which history a save lands in. That used to be the Save As dialog's
*default*, recomputed per save from the deck record -- and it was not stable
across two saves of one deck, which forked the history in half. The name is
held explicitly instead: the user sets it once, sees it, and can change it.

Three rules the rest of the app relies on:

**Empty means unset, and only empty.** A deck with no name holds ``""``. The
"no name yet" wording belongs to the UI and is never written here, never
persisted, and never becomes a deck key -- otherwise every unnamed deck would
share one history under the placeholder's own text.

**A name is always a legal file stem.** :func:`set_deck_name` sanitizes on the
way in, so callers never have to. What comes back out is exactly what will be
written to disk, which is what the UI shows.

**Renaming forks, and never rewrites.** The name decides the file; a new name
is a new file and therefore a new history. The old file and its repo are left
exactly as they were, so a rename can never orphan or rewrite versions the
user already has.
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

    This is what makes the change need no migration: a deck already on disk is
    keyed by its file's stem, and that stem is exactly the name it acquires
    here, so decks saved before the name existed keep the history they have.
    Never overwrites a name the user chose.
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
