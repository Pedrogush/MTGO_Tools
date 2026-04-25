"""Compact radar panel package.

Displays archetype card frequency in a small format, designed for embedding
in the opponent tracker overlay. Two view modes:
  - "Top Cards": Top 15 mainboard / 8 sideboard cards with inclusion rates
  - "Full Decklist": All cards as an average decklist (avg copies rounded)
"""

from __future__ import annotations

from widgets.panels.compact_radar_panel.frame import CompactRadarPanel
from widgets.panels.compact_radar_panel.properties import (
    _TOP_MAINBOARD_LIMIT,
    _TOP_SIDEBOARD_LIMIT,
    RadarViewMode,
)

__all__ = [
    "CompactRadarPanel",
    "RadarViewMode",
    "_TOP_MAINBOARD_LIMIT",
    "_TOP_SIDEBOARD_LIMIT",
]
