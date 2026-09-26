"""The deck's identity: the one thing about it the user cannot change.

A deck's version history is one git repo per deck, found by a key. That key used
to be the deck's *name* -- the one attribute the app invites the user to change.
Two things followed, both of them visible:

- **Renaming a deck emptied its history.** A new name is a new key is a repo
  with nothing in it, so the version graph vanished the moment the deck was
  called something else, with nothing on screen to say why.
- **Two decks with one name shared a history.** A named deck may live anywhere
  on disk (:func:`services.deck_name.deck_file_for`), so two ``Mono Red.txt`` in
  two folders keyed to the same repo and interleaved their saves into one
  branch, each one's diffs measured against the other's.

The id here is what the key is instead, and the name goes back to being what it
reads as: a label on the deck and the stem of its file.

**Why a uuid rather than the saved-decks row id.** The record already has an
``INTEGER PRIMARY KEY AUTOINCREMENT``, and reusing it would avoid a second key.
Two things rule it out. It does not exist until the database write succeeds, and
that write is best effort -- :meth:`DeckWorkflowService.save_deck` logs and
carries on when it fails, because a deck file already on disk must not be
reported as an unsaved deck, and the version has to be recorded under *some*
key by then. And the saved-decks database lives in ``cache/``, which a cache
clear or an uninstall throws away while the history (deliberately, see
:mod:`repositories.deck_vcs_repository.store`) survives -- after which the
counter restarts at 1 and the next deck ever saved would adopt a dead deck's
history. A uuid is never handed out twice, so the worst a lost database can do
is orphan a history; it can never mis-attach one.

The id lives on the in-memory deck record, which is what makes a rename free:
renaming mutates that same record, so the id -- and therefore the history --
comes with it. It is persisted in the ``deck_uuid`` column of the saved-decks
table, and read back onto the record whenever a deck file is loaded.
"""

from __future__ import annotations

import uuid
from typing import Any

#: Where the stable id lives on a deck record, and the name of the column
#: holding it. Spelled the same on both sides so a record read out of the
#: database carries it without any translation step.
DECK_ID_KEY = "deck_uuid"


def new_deck_id() -> str:
    """A fresh deck id: 32 hex characters, and a legal path segment as it stands."""
    return uuid.uuid4().hex


def deck_id_of(deck: dict[str, Any] | None) -> str:
    """``deck``'s stable id, or ``""`` when it has not been given one yet."""
    if not deck:
        return ""
    return str(deck.get(DECK_ID_KEY) or "").strip()


def set_deck_id(deck: dict[str, Any] | None, deck_id: str | None) -> str:
    """Put a known id on ``deck`` -- what loading a saved deck back does.

    Never overwrites an id the record already holds: the record in hand is the
    deck the user is looking at, and a lookup that returned somebody else's row
    (``find_saved_deck`` falls back to matching on deck *text*, which two decks
    can share) must not be able to re-point it at another history.
    """
    if deck is None:
        return ""
    existing = deck_id_of(deck)
    if existing:
        return existing
    cleaned = str(deck_id or "").strip()
    if not cleaned:
        return ""
    deck[DECK_ID_KEY] = cleaned
    return cleaned


def ensure_deck_id(deck: dict[str, Any] | None) -> str:
    """``deck``'s id, generating and stamping one if it has none.

    Called on the save path, which is the moment a deck stops being something
    on screen and becomes something the user keeps -- and therefore the moment
    it needs an identity that outlives its name.
    """
    if deck is None:
        return ""
    existing = deck_id_of(deck)
    if existing:
        return existing
    deck[DECK_ID_KEY] = new_deck_id()
    return deck[DECK_ID_KEY]


__all__ = [
    "DECK_ID_KEY",
    "deck_id_of",
    "ensure_deck_id",
    "new_deck_id",
    "set_deck_id",
]
