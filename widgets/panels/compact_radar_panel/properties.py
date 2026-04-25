"""View mode enum, module constants, and read-only accessors for the compact radar panel."""

from __future__ import annotations

from enum import Enum


class RadarViewMode(Enum):
    """View modes for the compact radar panel."""

    TOP_CARDS = "top"
    FULL_DECKLIST = "full"


_TOP_MAINBOARD_LIMIT = 15
_TOP_SIDEBOARD_LIMIT = 8


class CompactRadarPropertiesMixin:
    """Read-only accessors for :class:`CompactRadarPanel`.

    Kept as a mixin (no ``__init__``) so :class:`CompactRadarPanel` remains
    the single source of truth for instance-state initialization.
    """

    _view_mode: RadarViewMode

    @property
    def view_mode(self) -> RadarViewMode:
        return self._view_mode
