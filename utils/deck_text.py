"""The one line scanner and the one renderer every decklist in the app goes through.

A decklist is the app's interchange format: it arrives scraped, typed by hand,
edited in another program, averaged across a pool, or built from the zone
editor, and it leaves as a file MTGO and every rental bot can read. Three
modules had each grown their own copy of the same twenty-line loop over that
format -- the analysis parser, the deck-VCS normalizer and the collection diff
-- and the output format was hand-written in three more places. They disagreed,
and the disagreements were invisible until they bit: a ``.txt`` that merely
opened with a blank line normalized its entire maindeck into the sideboard on
one parser and not on the other, which is the kind of bug a second copy of a
loop exists to produce.

So the scanning lives here, once, and the two things callers genuinely differ on
are parameters rather than forks:

* **Printing ids.** ``services.deck_service.parser`` strips the trailing
  Scryfall pointer so name-based analysis keeps working; the deck-VCS
  normalizer must keep it, because it encodes the art the user chose and
  dropping it would silently discard that choice on every save.
* **The trailing newline.** A blob written into a git repo ends in exactly one
  newline so that appending it to a file and writing the file are the same
  bytes; text handed to a widget does not.

Why ``utils`` rather than ``services/deck_service``, which is where
``ARCHITECTURE.md`` puts deck parsing: the deck-VCS repository enforces the
normalization invariant at its single write site rather than trusting callers
to have normalized first, and a repository may not import a service. Moving the
enforcement up into the service layer would trade a structural guarantee for a
convention, which is the more expensive of the two things to lose. ``utils``
already hosts the cross-cutting half of this (``utils.deck.sanitize_filename``
is imported from both layers), so the parse primitive joins it and the shaped,
domain-specific readings stay where they are.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

#: The zone separator the app writes and every deck source we read emits.
SIDEBOARD_MARKER = "Sideboard"

# A count followed by the rest of the line, which is the name. Deliberately a
# pattern rather than ``line.split(" ", 1)`` plus ``float()``: that pair accepts
# "-2 Bolt", "1e3 Bolt" and -- worst -- "nan Bolt", any of which would travel
# all the way into a saved decklist, and it rejects a tab between the count and
# the name, which hand-edited files do contain. The name is captured verbatim;
# whether the printing-id pointer survives is the caller's call below.
_CARD_LINE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s+(\S.*?)\s*$")

# A trailing Scryfall printing-id pointer (``8-4-4-4-12`` hex), as emitted by the
# printing-selection helpers (see :mod:`services.deck_service.printing`). Set-code
# pointers are intentionally *not* stripped -- they need the printing index to be
# told apart from real names that happen to end in an upper-case token (e.g.
# "Look at Me, I'm the DCI").
_PRINTING_ID_SUFFIX = re.compile(
    r"\s+[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DeckEntry:
    """One card line as written, tagged with the zone it was written under."""

    count: float
    name: str
    is_sideboard: bool


def iter_entries(deck_text: str, *, strip_printing_id: bool = True) -> Iterator[DeckEntry]:
    """Yield every card line of *deck_text* in order, tagged by zone.

    Lines that are not card lines -- comments, headers, junk -- carry no deck
    content and are skipped. Either a blank line or a ``Sideboard`` marker opens
    the sideboard, because both spellings are in the wild and the app's own
    writer emits both.

    A blank line only separates zones once a card has been seen. A leading blank
    line separates nothing, and reading it as the zone break turned a file that
    merely opened with an empty line into a deck with no maindeck and its whole
    contents in the sideboard.
    """
    is_sideboard = False
    seen_a_card = False

    for raw_line in deck_text.split("\n"):
        line = raw_line.strip()

        if not line:
            if seen_a_card:
                is_sideboard = True
            continue

        if line.lower() == SIDEBOARD_MARKER.lower():
            is_sideboard = True
            continue

        match = _CARD_LINE.match(line)
        if match is None:
            continue

        name = match.group(2)
        if strip_printing_id:
            name = _PRINTING_ID_SUFFIX.sub("", name)
        yield DeckEntry(count=float(match.group(1)), name=name, is_sideboard=is_sideboard)
        seen_a_card = True


def format_count(count: float) -> str:
    """A count as a decklist writes it.

    Averaged decks carry fractional counts (:mod:`services.deck_service.averager`),
    so the integer case cannot just be assumed -- but neither can the fractional
    one, and "4.0 Lightning Bolt" is not a line any deck source produces.
    """
    return str(int(count)) if float(count).is_integer() else str(count)


def render_deck_text(
    mainboard: Iterable[tuple[float, str]],
    sideboard: Iterable[tuple[float, str]] = (),
    *,
    trailing_newline: bool = False,
) -> str:
    """``(count, name)`` pairs as deck text in the app's own format.

    Card lines, then a blank line, then ``Sideboard``, then card lines. The
    header is written even though a blank line alone would be understood, so a
    list with no maindeck lines still says which zone it is; the blank line is
    skipped when there is nothing above it to separate.

    An empty deck renders as the empty string rather than as a lone ``Sideboard``
    header or a bare newline, so "is there anything here?" stays answerable with
    a truth test on the result.
    """
    lines = [f"{format_count(count)} {name}" for count, name in mainboard]
    side_lines = [f"{format_count(count)} {name}" for count, name in sideboard]

    if not lines and not side_lines:
        return ""

    if side_lines:
        if lines:
            lines.append("")
        lines.append(SIDEBOARD_MARKER)
        lines.extend(side_lines)

    text = "\n".join(lines)
    return f"{text}\n" if trailing_newline else text


__all__ = [
    "SIDEBOARD_MARKER",
    "DeckEntry",
    "format_count",
    "iter_entries",
    "render_deck_text",
]
