"""Static data tables and mana-symbol SVG loading for the deck stats panel.

Pure module-level constants and asset loading with no panel dependency.
"""

from __future__ import annotations

from pathlib import Path

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

_TYPE_COLOURS: dict[str, str] = {
    "Land": "#917D5F",
    "Creature": "#5A87B9",
    "Instant": "#50A591",
    "Sorcery": "#7864AF",
    "Enchantment": "#A56E96",
    "Artifact": "#9B9BA5",
    "Planeswalker": "#5FA0B9",
    "Battle": "#AF735A",
    "Kindred": "#7A9E6A",
    "Other": "#828282",
}

# Opening-hand land count bar colours (0-7 lands)
# Accent blue for "good" outcomes (2-3 lands), muted gray-blue for bad outcomes.
_HAND_COLOURS = [
    "#4A5568",  # 0 – bad (muted gray-blue)
    "#4A5568",  # 1 – bad
    "#3B82F6",  # 2 – good (accent blue)
    "#3B82F6",  # 3 – good
    "#4A5568",  # 4 – bad
    "#4A5568",  # 5 – bad
    "#4A5568",  # 6 – bad
    "#4A5568",  # 7 – bad
]

# Mana curve gradient: light sky-blue (low CMC) → deep accent blue (high CMC).
_CURVE_WARM = (147, 197, 253)
_CURVE_COLD = (30, 64, 175)

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
            svg = svg.replace('fill="#444"', 'fill="#ECECEC"')
            # Strip the XML comment line to reduce HTML payload
            svg = "\n".join(line for line in svg.splitlines() if not line.startswith("<!--"))
            result[key] = svg.strip()
    return result


_COLOR_SVG_HTML: dict[str, str] = _load_mana_svgs()
