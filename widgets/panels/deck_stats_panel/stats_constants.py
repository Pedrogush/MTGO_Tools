"""Static data tables and mana-symbol SVG loading for the deck stats panel.

Pure module-level constants and asset loading with no panel dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

from utils.constants.theme import (
    CHART_OTHER,
    TEXT_PRIMARY,
    chart_palette,
    chart_ramp,
    to_hex,
)
from utils.constants.ui_images import (
    STATS_MANA_SVG_DISPLAY_SIZE,
    STATS_MANA_SVG_SOURCE_SIZE,
)

# The card types, rule 205.2a of the Comprehensive Rules:
#
#   "The card types are artifact, battle, conspiracy, creature, dungeon,
#    enchantment, instant, kindred, land, phenomenon, plane, planeswalker,
#    scheme, sorcery, and vanguard."
#
# The list is normative and closed -- there is no such type as "Other", which is
# what this chart used to show any card it failed to classify. Verified against
# the copy of the rules the app already ships (services.comp_rules_service's
# cache) by tests/test_deck_stats_types.py, so it cannot drift from them
# silently the way a hand-kept list does.
CARD_TYPES: tuple[str, ...] = (
    "Artifact",
    "Battle",
    "Conspiracy",
    "Creature",
    "Dungeon",
    "Enchantment",
    "Instant",
    "Kindred",
    "Land",
    "Phenomenon",
    "Plane",
    "Planeswalker",
    "Scheme",
    "Sorcery",
    "Vanguard",
)

#: The types a deck can be built out of, in the order the chart lists them:
#: mana first, then the spell types by how often a decklist holds them. Every
#: one of these gets a row even at zero, because "this deck runs no creatures"
#: is itself worth reading off the chart.
DECK_CARD_TYPES: tuple[str, ...] = (
    "Land",
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Battle",
    "Kindred",
)

#: The remaining rules types -- the non-traditional ones (rule 205.2b's
#: Conspiracy, Dungeon, Phenomenon, Plane, Scheme, Vanguard). They are real card
#: types and a card carrying one is classified, but no constructed decklist
#: holds them, so they earn a row only when one actually turns up.
OCCASIONAL_CARD_TYPES: tuple[str, ...] = tuple(t for t in CARD_TYPES if t not in DECK_CARD_TYPES)

#: Matching order: the chart's own order first, so ``_TYPE_COLOURS`` lines up
#: with the rows a deck actually produces.
_CARD_TYPES: tuple[str, ...] = DECK_CARD_TYPES + OCCASIONAL_CARD_TYPES

#: A type line is ``supertypes card-types — subtypes``, one such group per face.
#: Only the head of each face names card types; the tail names subtypes, and
#: those collide (there are creatures with the subtype "Dungeon", and "Plane" is
#: a prefix of "Planeswalker"), which is why this splits into words rather than
#: asking whether the type name appears anywhere in the string.
_TYPE_LINE_FACE_SPLIT = "//"
_TYPE_LINE_SUBTYPE_SPLIT_RE = re.compile(r"[\u2014\u2013-]")
_TYPE_LINE_WORD_RE = re.compile(r"[^A-Za-z]+")


def card_types_in(type_line: str | None) -> set[str]:
    """The rule 205.2a card types named on ``type_line``.

    A split card prints both halves in one line ("Instant // Sorcery") and is
    both, so every face is read.
    """
    words: set[str] = set()
    for face in (type_line or "").split(_TYPE_LINE_FACE_SPLIT):
        head = _TYPE_LINE_SUBTYPE_SPLIT_RE.split(face, maxsplit=1)[0]
        words.update(word for word in _TYPE_LINE_WORD_RE.split(head.lower()) if word)
    return {card_type for card_type in CARD_TYPES if card_type.lower() in words}


# MTG color identity → (full display label, hex bar colour)
_COLOR_MAP: dict[str, tuple[str, str]] = {
    "W": ("White", "#DCD2AA"),
    "U": ("Blue", "#3B82F6"),
    "B": ("Black", "#8C78A0"),
    "R": ("Red", "#D24632"),
    "G": ("Green", "#3CA046"),
    "C": ("Colorless", "#A0968A"),
    "Colorless": ("Colorless", "#A0968A"),
}

# Card-type bar colours. Ten off-palette hues until phase 8, none of them from
# phase 0's CVD-checked set and none of them measured against the chart ground.
# Now sliced from that set in the chart's own display order.
#
# More categories than the palette has hues means the tail wraps, which phase 0
# documented as the point past which "colour alone no longer identifies a
# category -- pair it with labels, ordering or a second channel". This chart
# does: every bar carries its type name and its count, and the order is fixed
# (_CARD_TYPES), so the wrapped hues land on the types a decklist almost never
# contains at all.
_TYPE_COLOURS: dict[str, str] = {
    card_type: to_hex(colour)
    for card_type, colour in zip(_CARD_TYPES, chart_palette(len(_CARD_TYPES)), strict=True)
}

# Opening-hand land-count bars (0..7 lands in the opener).
#
# This was ACCENT_PRIMARY for k in (2, 3) and #4A5568 for everything else --
# "good" vs "bad". Two things wrong with that, both fixed here:
#   * the accent as a good/bad categorical is a **third** colour register. Phase
#     2 shipped exactly two and named them: saturated fill = the one primary
#     action on a surface, 16% tint / 2px stroke = selected-or-current. A bar in
#     a probability chart is neither.
#   * "2-3 lands is good" is an editorial claim the chart never states and that
#     is false for a large part of the format -- a 17-land aggro deck and a
#     26-land control deck do not want the same opener.
# The axis is *ordinal* (0, 1, 2, ... lands), so it takes the sequential ramp.
# Colour now says where on the axis a bar sits, which is the one thing about it
# that is true independent of the deck.
_HAND_COLOURS = [to_hex(chart_ramp(k / 7)) for k in range(8)]

#: Swatch for a colour the data produced that ``_COLOR_MAP`` does not name. The
#: palette's neutral -- the swatch that exists to read as "not one of the
#: categories". Was a bare #828282 in properties.py, measuring 2.94:1 on the
#: chart ground.
_FALLBACK_SWATCH = to_hex(CHART_OTHER)

# Color key → mana SVG filename stem
_COLOR_SVG_FILENAMES: dict[str, str] = {
    "W": "w",
    "U": "u",
    "B": "b",
    "R": "r",
    "G": "g",
    "C": "c",
    "Colorless": "c",
}


def _load_mana_svgs() -> dict[str, str]:
    """Load and inline mana symbol SVGs for each color key, sized 18×18."""
    svg_dir = Path(__file__).parent.parent.parent.parent / "assets" / "mana" / "svg"
    result: dict[str, str] = {}
    for key, stem in _COLOR_SVG_FILENAMES.items():
        path = svg_dir / f"{stem}.svg"
        if path.exists():
            svg = path.read_text(encoding="utf-8")
            svg = svg.replace(
                f'width="{STATS_MANA_SVG_SOURCE_SIZE}" height="{STATS_MANA_SVG_SOURCE_SIZE}"',
                f'width="{STATS_MANA_SVG_DISPLAY_SIZE}" height="{STATS_MANA_SVG_DISPLAY_SIZE}"',
            )
            svg = svg.replace('fill="#444"', f'fill="{to_hex(TEXT_PRIMARY)}"')
            # Strip the XML comment line to reduce HTML payload
            svg = "\n".join(line for line in svg.splitlines() if not line.startswith("<!--"))
            result[key] = svg.strip()
    return result


_COLOR_SVG_HTML: dict[str, str] = _load_mana_svgs()
