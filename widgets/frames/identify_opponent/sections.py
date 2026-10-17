"""Which tracker sections are collapsed, and what that does to the layout.

The tracker has three sections -- the hypergeometric calculator and the radar
stacked in the left splitter, the sideboard guide in the right column -- and
each can be folded down to its heading. Everything here is wx-free (Humble
Object, ``tests/README.md`` §4): the frame hands in the measured heights and
applies what comes back.
"""

from __future__ import annotations

from collections.abc import Iterable

SECTION_CALCULATOR = "calculator"
SECTION_RADAR = "radar"
SECTION_GUIDE = "guide"

#: Every section that can be collapsed, in on-screen order.
SECTIONS: tuple[str, ...] = (SECTION_CALCULATOR, SECTION_RADAR, SECTION_GUIDE)

#: Config key the collapsed set is persisted under.
COLLAPSED_SECTIONS_KEY = "collapsed_sections"


def parse_collapsed_sections(raw: object) -> set[str]:
    """The collapsed set from a saved config value, ignoring anything unknown.

    The config file is hand-editable and outlives versions, so a non-list or a
    section name this build does not have is dropped rather than trusted.
    """
    if not isinstance(raw, list):
        return set()
    return {name for name in raw if isinstance(name, str) and name in SECTIONS}


def serialize_collapsed_sections(collapsed: Iterable[str]) -> list[str]:
    """The collapsed set as a stable, on-screen-ordered list for the config."""
    wanted = set(collapsed)
    return [name for name in SECTIONS if name in wanted]


def left_sash_target(
    *,
    calc_collapsed: bool,
    radar_collapsed: bool,
    calc_height: int,
    radar_height: int,
    splitter_height: int,
    sash_size: int,
) -> int:
    """Where the calculator/radar sash belongs for the given collapse state.

    ``calc_height`` and ``radar_height`` are each pane's best height *in its
    current state*, so a collapsed pane reports just its heading.

    - Calculator collapsed: the sash sits right under its heading, so the radar
      gets everything else (and, if the radar is collapsed too, its heading
      simply sits at the top of the space it was given).
    - Radar collapsed: the sash drops to just above the radar's heading, but
      never above the point where the calculator would be cut off.
    - Neither: the calculator gets exactly the height it needs, as before.
    """
    if calc_collapsed:
        return calc_height
    if radar_collapsed:
        return max(calc_height, splitter_height - radar_height - sash_size)
    return calc_height


def column_proportions(
    collapsed: Iterable[str], *, left_proportion: int, guide_proportion: int
) -> tuple[int, int]:
    """Sizer proportions for the (left column, guide column) pair.

    A column whose sections are all collapsed stops taking a share of the
    window's spare width, so the column that still has content gets it. If both
    columns are folded away there is nothing to give the width to, and the
    normal proportions stand.
    """
    folded = set(collapsed)
    left_folded = SECTION_CALCULATOR in folded and SECTION_RADAR in folded
    guide_folded = SECTION_GUIDE in folded
    if left_folded and guide_folded:
        return left_proportion, guide_proportion
    return (
        0 if left_folded else left_proportion,
        0 if guide_folded else guide_proportion,
    )
