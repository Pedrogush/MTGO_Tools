"""Pure column/cell-text helpers for :class:`DeckTableView`.

These functions hold the stateless math behind the table view's cells and
column widths so it can be unit-tested without any wx grid wiring:

* :func:`cell_text` formats one cell's display string from a card + metadata.
* :func:`fit_to_width` computes the Type/Text column widths that make the whole
  row fit the visible viewport, shrinking proportionally to each column's
  available room. It takes the natural widths (from autosize), the client
  width and the column indices and returns the new sizes for the view to
  apply — it never touches the grid itself.

Everything here is wx-independent (it only consumes the metadata dict and a few
ints) so it stays directly testable off-Windows where wx is unimportable.
"""

from __future__ import annotations

from typing import Any

from widgets.panels.card_table_panel.sorting import (
    COL_MANA,
    COL_NAME,
    COL_QTY,
    COL_TEXT,
    COL_TYPE,
    card_mana_value,
    card_type_line,
)

# Safety cap on raw oracle text stored in cells. The inline-symbol renderer
# does pixel-precise ellipsis truncation, but storing massive strings still
# costs memory in the grid table.
_MAX_TEXT_CHARS = 400

# Natural-width caps applied during AutoSize. fit_to_width then shrinks
# further so the whole row fits the visible viewport.
_MAX_TYPE_WIDTH = 220
# 540 gave the Text column ~420px in practice -- the widest column in the
# table, for the content that is truncated mid-sentence anyway and is the
# least glanceable thing in the row. Capped to something a reader can take
# in at a glance; the full text is in the card inspector.
_MAX_TEXT_WIDTH = 320
_MIN_TYPE_WIDTH = 60
# The narrowest oracle-text column still worth drawing. Below it the cell is an
# ellipsis and a letter, which tells the reader nothing while taking room from
# the columns that do.
_MIN_TEXT_WIDTH = 96
# ...and below that the column is dropped entirely rather than shrunk further.
# In a narrow deck workspace something has to give, and this is the content the
# card inspector always has in full.
_COLLAPSE_TEXT_BELOW = _MIN_TEXT_WIDTH
# Name joined the shrinkable set in phase 5. With Mana, Name, Qty and the
# actions column all unshrinkable, the row could not fit the deck workspace at
# its real width, so the trailing +/-/x controls were pushed off the right edge
# behind a horizontal scrollbar -- reachable only by scrolling.
_MIN_NAME_WIDTH = 110

# Per-column natural-width caps so a single huge value can't dominate.
COLUMN_WIDTH_CAPS: dict[str, int] = {COL_TYPE: _MAX_TYPE_WIDTH, COL_TEXT: _MAX_TEXT_WIDTH}


def cell_text(card: dict[str, Any], meta: Any, col_id: str) -> str:
    """Display string for ``card``'s ``col_id`` cell using its ``meta``."""
    if col_id == COL_QTY:
        return str(card.get("qty", 1))
    if col_id == COL_NAME:
        return str(card["name"])
    if col_id == COL_MANA:
        cost = meta.get("mana_cost")
        if cost:
            return cost
        mv = card_mana_value(meta)
        if mv == 0 and "land" in (card_type_line(meta) or "").lower():
            return ""
        return f"{{{int(mv)}}}"
    if col_id == COL_TYPE:
        return card_type_line(meta)
    if col_id == COL_TEXT:
        text = (meta.get("oracle_text") or "").replace("\n", " ")
        if len(text) > _MAX_TEXT_CHARS:
            return text[: _MAX_TEXT_CHARS - 1] + "…"
        return text
    return ""


def fit_to_width(
    natural_widths: dict[int, int],
    available: int,
    type_idx: int,
    text_idx: int,
    name_idx: int | None = None,
) -> dict[int, int]:
    """Shrinkable-column widths that make the row fit ``available`` px.

    Starts from ``natural_widths`` (the autosize baseline) and distributes the
    overflow across Text, Type and Name proportionally to the room each has above
    its own minimum. Mana, Qty and the trailing actions column are never shrunk:
    the first two are icon/numeric columns with no filler, and the third hosts
    fixed-size controls.

    Returns a mapping of column index -> new size for *only* the columns that
    change. An empty mapping means no shrink is needed (and the caller should
    restore the natural widths). The grid is never mutated here.
    """
    if not natural_widths or available <= 0:
        return {}
    overflow = sum(natural_widths.values()) - available
    if overflow <= 0:
        return {}

    def room(idx: int | None, minimum: int) -> int:
        if idx is None:
            return 0
        return max(0, natural_widths.get(idx, 0) - minimum)

    result: dict[int, int] = {}
    text_size = natural_widths.get(text_idx, 0)
    room_with_text = (
        room(text_idx, _MIN_TEXT_WIDTH)
        + room(type_idx, _MIN_TYPE_WIDTH)
        + room(name_idx, _MIN_NAME_WIDTH)
    )
    if text_size and overflow > room_with_text:
        # Every column is already at its minimum and the row still does not fit.
        # Shrinking Text below its legibility floor would leave an ellipsis and
        # one letter, so drop the column instead and re-shrink the rest.
        result[text_idx] = 0
        overflow -= text_size
        if overflow <= 0:
            return result

    # Ordered widest-filler-first: Text is mostly filler, Name is mostly not, so
    # a proportional split across all three still takes the most from Text.
    shrinkable = [] if text_idx in result else [(text_idx, _MIN_TEXT_WIDTH)]
    shrinkable.append((type_idx, _MIN_TYPE_WIDTH))
    if name_idx is not None:
        shrinkable.append((name_idx, _MIN_NAME_WIDTH))

    rooms = {idx: max(0, natural_widths.get(idx, 0) - minimum) for idx, minimum in shrinkable}
    total_room = sum(rooms.values())
    if total_room <= 0:
        return result

    take = min(overflow, total_room)
    remaining = take
    for position, (idx, _minimum) in enumerate(shrinkable):
        size = natural_widths.get(idx, 0)
        if not size:
            continue
        if position == len(shrinkable) - 1:
            share = min(remaining, rooms[idx])
        else:
            share = min(remaining, int(round(take * rooms[idx] / total_room)))
        result[idx] = size - share
        remaining -= share
    return result
