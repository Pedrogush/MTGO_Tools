"""The one canonical decklist form every write path in this package goes through.

Git diffs by line, so a decklist that is written in whatever order the UI happens
to hold its zones in produces a diff full of moved lines the moment anything is
reordered -- noise that buries the two cards that actually changed. Normalizing
on every write makes line order a function of the deck's *content* alone, so a
diff between two commits shows exactly the cards that differ and nothing else.

That makes this module load-bearing rather than cosmetic: :func:`normalize_decklist`
is the only thing that may produce text destined for a deck repo, and
:func:`decklist_fingerprint` -- which hashes that same normalized form -- is what
lets an externally edited ``.txt`` be recognised as a decklist already committed.

The output is deliberately the same shape the app already writes
(``utils.deck_text.render_deck_text``, which is also what the zone editor and the
collection diff render through): card lines, then a blank line, then
``Sideboard``, then card lines. It stays an ordinary decklist that Manatraders,
MTGO and every other external tool reads, which is the constraint the whole
feature is built under -- no version metadata ever enters the file.

What this module adds over that shared scanner is the *canonical* part: totals
per zone, sorted. The one thing it asks of the scanner is that the trailing
Scryfall printing-id pointer survives, because it encodes the art the user chose
(see :mod:`services.deck_service.printing`) and stripping it the way the
analysis parser does would silently discard that choice on every save.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from utils.deck_text import SIDEBOARD_MARKER, iter_entries, render_deck_text

__all__ = [
    "SIDEBOARD_MARKER",
    "NormalizedEntry",
    "decklist_fingerprint",
    "normalize_decklist",
    "parse_entries",
]


@dataclass(frozen=True)
class NormalizedEntry:
    """One aggregated card line in canonical form."""

    count: float
    name: str
    is_sideboard: bool


def parse_entries(deck_text: str) -> list[NormalizedEntry]:
    """Card lines of ``deck_text``, aggregated per zone and sorted canonically.

    Duplicate lines for the same name inside one zone are summed, so a list that
    says ``2 Consider`` twice and one that says ``4 Consider`` normalize to the
    same text -- and therefore to the same commit.
    """
    main: dict[str, float] = {}
    side: dict[str, float] = {}

    for entry in iter_entries(deck_text, strip_printing_id=False):
        target = side if entry.is_sideboard else main
        target[entry.name] = target.get(entry.name, 0.0) + entry.count

    return [
        *(_entries_for(main, is_sideboard=False)),
        *(_entries_for(side, is_sideboard=True)),
    ]


def _entries_for(totals: dict[str, float], *, is_sideboard: bool) -> list[NormalizedEntry]:
    # Case-insensitive first so "brazen borrower" and "Brazen Borrower" sort
    # together, then the exact name so the order is total (and therefore stable)
    # when two names differ only in case.
    names = sorted(totals, key=lambda name: (name.casefold(), name))
    return [
        NormalizedEntry(count=totals[name], name=name, is_sideboard=is_sideboard)
        for name in names
        if totals[name] > 0
    ]


def normalize_decklist(deck_text: str) -> str:
    """``deck_text`` in canonical form: sorted, aggregated, one card per line.

    The result always ends in exactly one newline, so appending a commit's blob
    to a file and writing it back are the same bytes.
    """
    entries = parse_entries(deck_text)
    return render_deck_text(
        [(entry.count, entry.name) for entry in entries if not entry.is_sideboard],
        [(entry.count, entry.name) for entry in entries if entry.is_sideboard],
        trailing_newline=True,
    )


def decklist_fingerprint(deck_text: str) -> str:
    """A content hash of ``deck_text``'s canonical form.

    Two decklists that differ only in card order, duplicate lines, zone marker
    spelling or trailing whitespace share a fingerprint, which is what makes
    "has this externally edited file already been committed?" answerable without
    walking blobs by hand.
    """
    return hashlib.sha256(normalize_decklist(deck_text).encode("utf-8")).hexdigest()
