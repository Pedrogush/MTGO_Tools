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
(``services.deck_service.text_builder``): card lines, then a blank line, then
``Sideboard``, then card lines. It stays an ordinary decklist that Manatraders,
MTGO and every other external tool reads, which is the constraint the whole
feature is built under -- no version metadata ever enters the file.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

SIDEBOARD_MARKER = "Sideboard"

# A count followed by the rest of the line. The name is kept verbatim -- including
# any trailing Scryfall printing-id pointer, which encodes the art the user chose
# (see :mod:`services.deck_service.printing`). Stripping it the way the analysis
# parser does would silently discard that choice on every save.
_CARD_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s+(\S.*?)\s*$")


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
    is_sideboard = False
    seen_a_card = False

    for raw_line in deck_text.split("\n"):
        line = raw_line.strip()
        if not line:
            # The app's own writer separates the zones with a blank line, so a
            # blank line starts the sideboard exactly as the analysis parser
            # treats it (services/deck_service/parser.py::_iter_entries) --
            # which strips the text first, so a blank line before the first card
            # separates nothing there. It has to separate nothing here too: a
            # file that merely opens with an empty line was otherwise read as a
            # deck with no maindeck and its whole contents in the sideboard.
            if seen_a_card:
                is_sideboard = True
            continue
        if line.lower() == SIDEBOARD_MARKER.lower():
            is_sideboard = True
            continue

        match = _CARD_LINE.match(line)
        if match is None:
            # Not a card line (a comment, a header, junk). It carries no deck
            # content, and keeping it would make line order depend on something
            # other than the cards -- which is the noise this module exists to
            # remove.
            continue

        count = float(match.group(1))
        name = match.group(2)
        target = side if is_sideboard else main
        target[name] = target.get(name, 0.0) + count
        seen_a_card = True

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


def _format_count(count: float) -> str:
    # Averaged decks carry fractional counts (services/deck_service/averager.py),
    # so the integer case cannot just be assumed.
    return str(int(count)) if float(count).is_integer() else str(count)


def normalize_decklist(deck_text: str) -> str:
    """``deck_text`` in canonical form: sorted, aggregated, one card per line.

    The result always ends in exactly one newline, so appending a commit's blob
    to a file and writing it back are the same bytes.
    """
    entries = parse_entries(deck_text)
    if not entries:
        return ""

    main_lines = [
        f"{_format_count(entry.count)} {entry.name}" for entry in entries if not entry.is_sideboard
    ]
    side_lines = [
        f"{_format_count(entry.count)} {entry.name}" for entry in entries if entry.is_sideboard
    ]

    lines = list(main_lines)
    if side_lines:
        if lines:
            lines.append("")
        lines.append(SIDEBOARD_MARKER)
        lines.extend(side_lines)
    return "\n".join(lines) + "\n"


def decklist_fingerprint(deck_text: str) -> str:
    """A content hash of ``deck_text``'s canonical form.

    Two decklists that differ only in card order, duplicate lines, zone marker
    spelling or trailing whitespace share a fingerprint, which is what makes
    "has this externally edited file already been committed?" answerable without
    walking blobs by hand.
    """
    return hashlib.sha256(normalize_decklist(deck_text).encode("utf-8")).hexdigest()
