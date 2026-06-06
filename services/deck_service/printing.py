"""Printing-aware decklist parsing and conversion helpers.

A *printing index* is a mapping ``name_lower -> [printing, ...]`` where each
printing is a dict-like object exposing at least ``id`` (Scryfall UUID),
``set`` (upper-case set/edition code), ``released_at`` (``YYYY-MM-DD``) and,
optionally, ``full_art``. This is exactly the shape produced by
:func:`services.image_service.printing_index.build_printing_index` and carried
on the running app as ``ImageService.bulk_data_by_name``.

Decklist lines support these pointer-aware formats (``N`` may be written
``Nx``)::

    N CARD_NAME PRINTING_ID     # an exact Scryfall printing UUID
    N CARD_NAME EDITION         # a set code such as ROE / RAV / EOE
    N CARD_NAME                 # printing-agnostic

On load (:func:`format_decklist_on_load`) a decklist is normalised to the
*most restrictive format that fits every valid card*: printing-id only when
every card resolves to a valid printing id, edition when every card resolves at
least to an edition, otherwise agnostic. Lines whose card name cannot be
resolved are dropped with a warning rather than raising.

The ``decklist_with_*`` helpers re-pick a printing per card by some rule
(oldest / newest / full-art / by-date / after-date) and render the result with
printing-id pointers, falling back to agnostic (with a warning) when no
suitable printing exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import IntEnum
from typing import Any

from loguru import logger

PrintingIndex = Mapping[str, Sequence[Mapping[str, Any]]]

# Magic: The Gathering's first set (Limited Edition Alpha) shipped in 1993.
MTG_RELEASE_YEAR = 1993


class _Level(IntEnum):
    """How precisely a parsed line pins down a printing (higher == stricter)."""

    AGNOSTIC = 0
    EDITION = 1
    PRINTING_ID = 2


@dataclass(frozen=True)
class _Resolution:
    """Result of resolving a line's card name + optional printing pointer."""

    name: str
    level: _Level
    token: str | None  # the printing id or edition code to render, if any
    printing: Mapping[str, Any] | None  # the matched printing (for downgrades)
    valid: bool  # whether ``name`` is a known card in the index


@dataclass(frozen=True)
class ParsedCard:
    """A decklist line split into quantity, card name and zone."""

    count: float
    name: str
    is_sideboard: bool


# ---------------------------------------------------------------------------
# Low-level line parsing
# ---------------------------------------------------------------------------


def _parse_count(token: str) -> float | None:
    """Parse a quantity token, accepting both ``4`` and ``4x`` styles."""
    candidate = token[:-1] if token[-1:].lower() == "x" else token
    try:
        return float(candidate)
    except ValueError:
        return None


def _format_count(count: float) -> str:
    """Render a quantity, dropping a redundant ``.0`` on whole numbers."""
    return str(int(count)) if float(count).is_integer() else str(count)


def _split_line(line: str) -> tuple[float, str] | None:
    """Split a card line into ``(count, rest)`` or ``None`` for non-card lines."""
    parts = line.split(" ", 1)
    if len(parts) < 2:
        return None
    count = _parse_count(parts[0])
    rest = parts[1].strip()
    if count is None or not rest:
        return None
    return count, rest


def _find_printing_by_id(printings: Sequence[Mapping[str, Any]], token: str) -> Mapping | None:
    lowered = token.lower()
    for printing in printings:
        if str(printing.get("id") or "").lower() == lowered:
            return printing
    return None


def _find_printing_by_set(printings: Sequence[Mapping[str, Any]], token: str) -> Mapping | None:
    upper = token.upper()
    for printing in printings:
        if str(printing.get("set") or "").upper() == upper:
            return printing
    return None


def _resolve(rest: str, index: PrintingIndex) -> _Resolution:
    """Resolve a line body (everything after the quantity) against the index.

    Preference order, so that legitimate multi-word names always win over an
    accidental trailing-token interpretation:

    1. The whole body is a known card name -> agnostic (no pointer).
    2. ``... TRAILING`` where the leading words are a known name and the
       trailing token is a valid printing id / edition for that name.
    3. The leading words are a known name but the trailing token resolves to
       nothing -> keep the name, drop the (invalid) pointer.
    4. Otherwise the name is unknown.
    """
    if rest.lower() in index:
        return _Resolution(rest, _Level.AGNOSTIC, None, None, valid=True)

    tokens = rest.split()
    if len(tokens) >= 2:
        base = " ".join(tokens[:-1])
        last = tokens[-1]
        printings = index.get(base.lower())
        if printings is not None:
            by_id = _find_printing_by_id(printings, last)
            if by_id is not None:
                return _Resolution(base, _Level.PRINTING_ID, str(by_id.get("id")), by_id, True)
            by_set = _find_printing_by_set(printings, last)
            if by_set is not None:
                return _Resolution(base, _Level.EDITION, last.upper(), by_set, True)
            # Trailing token looked like a pointer but matched nothing; the base
            # name is still valid, so keep it as an agnostic entry.
            return _Resolution(base, _Level.AGNOSTIC, None, None, valid=True)

    return _Resolution(rest, _Level.AGNOSTIC, None, None, valid=False)


def _iter_resolved(text: str, index: PrintingIndex):
    """Yield ``(count, is_sideboard, _Resolution)`` for every card line."""
    is_sideboard = False
    for raw in text.strip().split("\n"):
        line = raw.strip()
        if not line:
            is_sideboard = True
            continue
        if line.lower() == "sideboard":
            is_sideboard = True
            continue
        parsed = _split_line(line)
        if parsed is None:
            continue
        count, rest = parsed
        yield count, is_sideboard, _resolve(rest, index)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _render_line(count: float, name: str, token: str | None) -> str:
    base = f"{_format_count(count)} {name}"
    return f"{base} {token}" if token else base


def _render(rows: Sequence[tuple[float, str, bool, str | None]]) -> str:
    """Render rows of ``(count, name, is_sideboard, token)`` to deck text."""
    main = [(c, n, t) for c, n, sb, t in rows if not sb]
    side = [(c, n, t) for c, n, sb, t in rows if sb]
    lines = [_render_line(c, n, t) for c, n, t in main]
    if side:
        lines.append("")
        lines.append("Sideboard")
        lines.extend(_render_line(c, n, t) for c, n, t in side)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public: parsing
# ---------------------------------------------------------------------------


def parse_printed_decklist(text: str, index: PrintingIndex) -> list[ParsedCard]:
    """Parse decklist text into resolved cards, dropping unknown names.

    Card names are resolved against ``index`` so that trailing printing-id /
    edition pointers are stripped from the returned :class:`ParsedCard.name`.
    Lines whose card name is unknown are skipped with a warning.
    """
    cards: list[ParsedCard] = []
    for count, is_sideboard, res in _iter_resolved(text, index):
        if not res.valid:
            logger.warning(f"Ignoring decklist line with unknown card: {res.name!r}")
            continue
        cards.append(ParsedCard(count=count, name=res.name, is_sideboard=is_sideboard))
    return cards


# ---------------------------------------------------------------------------
# Public: format on load
# ---------------------------------------------------------------------------


def format_decklist_on_load(text: str, index: PrintingIndex) -> str:
    """Normalise a decklist to the most restrictive format that fits all cards.

    Unknown card names are dropped with a warning. The whole decklist is then
    rendered at a single uniform precision: printing ids only if *every* card
    has one, editions if every card has at least an edition, otherwise
    agnostic.
    """
    rows: list[tuple[float, bool, _Resolution]] = []
    for count, is_sideboard, res in _iter_resolved(text, index):
        if not res.valid:
            logger.warning(f"Ignoring decklist line with unknown card: {res.name!r}")
            continue
        rows.append((count, is_sideboard, res))

    if not rows:
        return ""

    levels = [res.level for _, _, res in rows]
    if all(level == _Level.PRINTING_ID for level in levels):
        deck_level = _Level.PRINTING_ID
    elif all(level >= _Level.EDITION for level in levels):
        deck_level = _Level.EDITION
    else:
        deck_level = _Level.AGNOSTIC

    out: list[tuple[float, str, bool, str | None]] = []
    for count, is_sideboard, res in rows:
        if deck_level == _Level.AGNOSTIC:
            token = None
        elif deck_level == _Level.PRINTING_ID:
            token = res.token
        else:  # EDITION — a printing-id line is downgraded to its set code.
            if res.level == _Level.EDITION:
                token = res.token
            else:
                token = str((res.printing or {}).get("set") or "").upper() or None
        out.append((count, res.name, is_sideboard, token))
    return _render(out)


# ---------------------------------------------------------------------------
# Public: printing-selection conversions
# ---------------------------------------------------------------------------


def _coerce_date(value: Any) -> date | None:
    """Best-effort coercion of a date-ish value to a :class:`datetime.date`."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value.strip()
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    return None


def _released_date(printing: Mapping[str, Any]) -> date | None:
    return _coerce_date(printing.get("released_at"))


def _select_by_rule(text: str, index: PrintingIndex, rule, *, rule_name: str) -> str:
    """Apply a per-card ``rule(printings) -> printing | None`` selector.

    ``rule`` receives the full printing list for a card and returns the chosen
    printing, or ``None`` to fall back to agnostic (with a warning).
    """
    rows: list[tuple[float, str, bool, str | None]] = []
    for count, is_sideboard, res in _iter_resolved(text, index):
        printings = list(index.get(res.name.lower()) or [])
        chosen = rule(printings) if printings else None
        if chosen is None:
            if res.valid:
                logger.warning(f"No {rule_name} printing for {res.name!r}; leaving it agnostic")
            else:
                logger.warning(f"Unknown card {res.name!r}; leaving it agnostic")
            rows.append((count, res.name, is_sideboard, None))
        else:
            rows.append((count, res.name, is_sideboard, str(chosen.get("id")) or None))
    return _render(rows)


def decklist_with_oldest_printings(text: str, index: PrintingIndex) -> str:
    """Pin every card to its earliest-released printing."""

    def rule(printings):
        dated = [p for p in printings if _released_date(p) is not None]
        return min(dated, key=lambda p: _released_date(p)) if dated else None

    return _select_by_rule(text, index, rule, rule_name="oldest")


def decklist_with_newest_printings(text: str, index: PrintingIndex) -> str:
    """Pin every card to its latest-released printing."""

    def rule(printings):
        dated = [p for p in printings if _released_date(p) is not None]
        return max(dated, key=lambda p: _released_date(p)) if dated else None

    return _select_by_rule(text, index, rule, rule_name="newest")


def decklist_with_full_art_printings(text: str, index: PrintingIndex) -> str:
    """Pin every card to its newest full-art printing, when one exists."""

    def rule(printings):
        full = [p for p in printings if p.get("full_art") and _released_date(p) is not None]
        return max(full, key=lambda p: _released_date(p)) if full else None

    return _select_by_rule(text, index, rule, rule_name="full-art")


def decklist_with_newest_printings_by(text: str, index: PrintingIndex, when: Any) -> str:
    """Pin every card to the newest printing released on or before ``when``.

    Returns the agnostic decklist (with a warning) when ``when`` is invalid,
    predates Magic's 1993 debut, or when *any* card has no printing by that
    date.
    """
    cutoff = _coerce_date(when)
    if cutoff is None:
        logger.warning(f"Invalid date {when!r} for newest-by; returning agnostic decklist")
        return decklist_with_printings_to_agnostic(text, index)
    if cutoff.year < MTG_RELEASE_YEAR:
        logger.warning(f"Date {cutoff} predates Magic ({MTG_RELEASE_YEAR}); returning agnostic")
        return decklist_with_printings_to_agnostic(text, index)

    rows: list[tuple[float, str, bool, str | None]] = []
    for count, is_sideboard, res in _iter_resolved(text, index):
        eligible = [
            p
            for p in index.get(res.name.lower()) or []
            if (d := _released_date(p)) is not None and d <= cutoff
        ]
        if not eligible:
            logger.warning(f"No printing of {res.name!r} by {cutoff}; returning agnostic decklist")
            return decklist_with_printings_to_agnostic(text, index)
        chosen = max(eligible, key=lambda p: _released_date(p))
        rows.append((count, res.name, is_sideboard, str(chosen.get("id")) or None))
    return _render(rows)


def decklist_with_printings_after(text: str, index: PrintingIndex, when: Any) -> str:
    """Pin every card to its first printing released strictly after ``when``.

    Returns the agnostic decklist (with a warning) when ``when`` is invalid or
    when *any* card has no printing after that date.
    """
    cutoff = _coerce_date(when)
    if cutoff is None:
        logger.warning(f"Invalid date {when!r} for printings-after; returning agnostic decklist")
        return decklist_with_printings_to_agnostic(text, index)

    rows: list[tuple[float, str, bool, str | None]] = []
    for count, is_sideboard, res in _iter_resolved(text, index):
        eligible = [
            p
            for p in index.get(res.name.lower()) or []
            if (d := _released_date(p)) is not None and d > cutoff
        ]
        if not eligible:
            logger.warning(
                f"No printing of {res.name!r} after {cutoff}; returning agnostic decklist"
            )
            return decklist_with_printings_to_agnostic(text, index)
        chosen = min(eligible, key=lambda p: _released_date(p))
        rows.append((count, res.name, is_sideboard, str(chosen.get("id")) or None))
    return _render(rows)


def decklist_with_printings_to_agnostic(text: str, index: PrintingIndex) -> str:
    """Strip all printing pointers, leaving ``N CARD_NAME`` lines."""
    rows = [
        (count, res.name, is_sideboard, None)
        for count, is_sideboard, res in _iter_resolved(text, index)
    ]
    return _render(rows)


__all__ = [
    "MTG_RELEASE_YEAR",
    "ParsedCard",
    "PrintingIndex",
    "decklist_with_full_art_printings",
    "decklist_with_newest_printings",
    "decklist_with_newest_printings_by",
    "decklist_with_oldest_printings",
    "decklist_with_printings_after",
    "decklist_with_printings_to_agnostic",
    "format_decklist_on_load",
    "parse_printed_decklist",
]
