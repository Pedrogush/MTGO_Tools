"""Compact mode for the opponent tracker: what the floating chip shows, and where.

In compact mode the tracker window hides and a small always-on-top chip takes
its place, meant to sit by the opponent's portrait in the MTGO match window.
The chip shows the opponent archetype's initials; hovering it opens a card with
the tracker's headline, the radar's top cards and the sideboard plan.

Everything here is wx-free (Humble Object, ``tests/README.md`` §4); the chip
widget and the frame mixin apply what it decides.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

#: Config keys, saved beside the window position.
COMPACT_MODE_KEY = "compact_mode"
CHIP_POSITION_KEY = "compact_chip_pos"
CHIP_LOCKED_KEY = "compact_chip_locked"

#: Where the chip starts, as a fraction of the MTGO match window's width and
#: height measured from its top-left corner. MTGO does not report where it
#: draws the opponent's portrait, so this is an estimate of "just under the
#: opponent's avatar in the top-left player panel" on the default layout. The
#: chip is free-floating: unlock it and drag it if the guess is off, and the
#: dragged spot is what gets remembered.
PORTRAIT_GUESS_FRACTION = (0.01, 0.22)

#: Lines of each section shown in the hover card; the full list stays in the
#: full tracker window.
HOVER_SECTION_LINE_LIMIT = 14

#: Sentinel the tracker's lookups use for "no deck in this format".
_UNKNOWN = "Unknown"


class ChipState:
    """What the chip's status dot says."""

    IDLE = "idle"  # no opponent detected
    UNKNOWN = "unknown"  # opponent detected, no recent deck found
    KNOWN = "known"  # opponent's archetype known


@dataclass(frozen=True)
class ChipFace:
    label: str
    state: str


def archetype_initials(archetype: str, *, limit: int = 3) -> str:
    """Up to ``limit`` capital initials: "Gruul Basking Broodscale" -> "GBB".

    A one-word archetype keeps its first ``limit`` letters ("Burn" -> "BUR"),
    since a single initial says nothing.
    """
    words = [w for w in archetype.replace("-", " ").split() if w[:1].isalnum()]
    if not words:
        return "?"
    if len(words) == 1:
        return words[0][:limit].upper()
    return "".join(w[0] for w in words[:limit]).upper()


def chip_face(player_name: str, decks: dict[str, str]) -> ChipFace:
    """The chip's label and status for the tracker's current opponent.

    Uses the same deck the radar loads (the first format with a known deck), so
    the chip and the hover card's radar always name the same archetype.
    """
    if not player_name:
        return ChipFace("–", ChipState.IDLE)
    for archetype in decks.values():
        if archetype and archetype != _UNKNOWN:
            return ChipFace(archetype_initials(archetype), ChipState.KNOWN)
    return ChipFace("?", ChipState.UNKNOWN)


Rect = tuple[int, int, int, int]  # x, y, width, height


def clamp_to_area(x: int, y: int, size: tuple[int, int], area: Rect) -> tuple[int, int]:
    """Keep a window of ``size`` at (x, y) wholly inside ``area``."""
    ax, ay, aw, ah = area
    w, h = size
    x = max(ax, min(x, ax + aw - w))
    y = max(ay, min(y, ay + ah - h))
    return x, y


def initial_chip_position(
    *,
    chip_size: tuple[int, int],
    display_area: Rect,
    saved: object = None,
    match_window: Rect | None = None,
    fallback_anchor: Rect | None = None,
) -> tuple[int, int]:
    """Where the chip appears when compact mode turns on.

    In order of preference: the spot the user dragged it to last time; the
    guessed portrait spot in the MTGO match window; just inside the tracker
    window's top-left corner (where the user was looking); the display's corner.
    Always clamped onto ``display_area`` so a saved spot from a since-unplugged
    monitor cannot strand the chip off screen.
    """
    position: tuple[int, int] | None = None
    if isinstance(saved, (list, tuple)) and len(saved) == 2:
        try:
            position = (int(saved[0]), int(saved[1]))
        except (TypeError, ValueError):
            position = None
    if position is None and match_window is not None:
        mx, my, mw, mh = match_window
        fx, fy = PORTRAIT_GUESS_FRACTION
        position = (mx + round(mw * fx), my + round(mh * fy))
    if position is None and fallback_anchor is not None:
        position = (fallback_anchor[0], fallback_anchor[1])
    if position is None:
        position = (display_area[0], display_area[1])
    return clamp_to_area(position[0], position[1], chip_size, display_area)


def popup_position(
    chip_rect: Rect, popup_size: tuple[int, int], display_area: Rect, *, gap: int = 4
) -> tuple[int, int]:
    """Open the hover card to the right of the chip, or to its left if there
    is no room, top-aligned with it and kept on the display."""
    cx, cy, cw, _ch = chip_rect
    pw, _ph = popup_size
    ax, _ay, aw, _ah = display_area
    x = cx + cw + gap
    if x + pw > ax + aw:
        x = cx - gap - pw
    return clamp_to_area(x, cy, popup_size, display_area)


@dataclass(frozen=True)
class HoverSection:
    heading: str
    lines: tuple[str, ...]


def hover_section(
    heading: str, lines: Iterable[str], *, limit: int = HOVER_SECTION_LINE_LIMIT
) -> HoverSection:
    """A hover-card section: the pane's heading and its first ``limit`` lines.

    Blank trailing lines are dropped and a cut list says how much is left, so
    the card never ends on a separator or silently hides the rest.
    """
    kept = list(lines)
    while kept and not kept[-1].strip():
        kept.pop()
    if len(kept) > limit:
        hidden = len(kept) - limit
        kept = kept[:limit] + [f"… +{hidden} more"]
    return HoverSection(heading, tuple(kept))


def hover_sections(sections: Sequence[tuple[str, Iterable[str]]]) -> list[HoverSection]:
    """The hover card's sections, skipping any with nothing to show."""
    built = [hover_section(heading, lines) for heading, lines in sections]
    return [s for s in built if s.lines]
