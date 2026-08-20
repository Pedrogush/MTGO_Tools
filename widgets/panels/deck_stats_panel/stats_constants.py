"""Static data tables and mana-symbol SVG loading for the deck stats panel.

Pure module-level constants and asset loading with no panel dependency.
"""

from __future__ import annotations

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

_CARD_TYPES = [
    "Land",
    "Creature",
    "Instant",
    "Sorcery",
    "Enchantment",
    "Artifact",
    "Planeswalker",
    "Battle",
    "Kindred",
]

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
# Now sliced from that set in the chart's own display order, with the aggregate
# "Other" bucket taking the palette's neutral -- the swatch that exists to read
# as "not a category".
#
# Ten categories against a palette of seven hues means the tail wraps, which
# phase 0 documented as the point past which "colour alone no longer identifies
# a category -- pair it with labels, ordering or a second channel". This chart
# does: every bar carries its type name and its count, and the order is fixed
# (_CARD_TYPES), so the two wrapped hues land on Battle and Kindred, the two
# types a Modern/Legacy decklist almost never contains at all.
_TYPE_COLOURS: dict[str, str] = {
    **{
        card_type: to_hex(colour)
        for card_type, colour in zip(_CARD_TYPES, chart_palette(len(_CARD_TYPES)), strict=True)
    },
    "Other": to_hex(CHART_OTHER),
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

#: Swatch for a colour or card type the data produced that neither table names.
#: The palette's neutral, i.e. the same swatch the aggregate "Other" bucket
#: takes -- an unrecognised value *is* the aggregate bucket. Was a bare #828282
#: at two call sites in properties.py, measuring 2.94:1 on the chart ground.
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
