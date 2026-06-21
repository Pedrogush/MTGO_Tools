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
    COL_COLOR,
    COL_MANA,
    COL_NAME,
    COL_TEXT,
    COL_TYPE,
    card_colors,
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
_MAX_TEXT_WIDTH = 540
_MIN_TYPE_WIDTH = 70
_MIN_TEXT_WIDTH = 100

# Per-column natural-width caps so a single huge value can't dominate.
COLUMN_WIDTH_CAPS: dict[str, int] = {COL_TYPE: _MAX_TYPE_WIDTH, COL_TEXT: _MAX_TEXT_WIDTH}


def cell_text(card: dict[str, Any], meta: Any, col_id: str) -> str:
    """Display string for ``card``'s ``col_id`` cell using its ``meta``."""
    if col_id == COL_NAME:
        qty = card.get("qty", 1)
        return f"{qty}× {card['name']}"
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
    if col_id == COL_COLOR:
        cols = card_colors(meta)
        if not cols:
            return "{C}"
        return "".join(f"{{{c}}}" for c in cols)
    return ""


def fit_to_width(
    natural_widths: dict[int, int],
    available: int,
    type_idx: int,
    text_idx: int,
) -> dict[int, int]:
    """Type/Text widths that shrink the row to fit ``available`` px.

    Starts from ``natural_widths`` (the autosize baseline) and distributes the
    overflow between the Type and Text columns proportionally to the room each
    has above its minimum. Other columns (mana, name, color) are never shrunk.

    Returns a mapping of column index -> new size for *only* the columns that
    change. An empty mapping means no shrink is needed (and the caller should
    restore the natural widths). The grid is never mutated here.
    """
    if not natural_widths or available <= 0:
        return {}
    total = sum(natural_widths.values())
    overflow = total - available
    if overflow <= 0:
        return {}
    type_size = natural_widths.get(type_idx, 0)
    text_size = natural_widths.get(text_idx, 0)
    type_room = max(0, type_size - _MIN_TYPE_WIDTH)
    text_room = max(0, text_size - _MIN_TEXT_WIDTH)
    total_room = type_room + text_room
    if total_room <= 0:
        return {}
    take = min(overflow, total_room)
    # Text has more filler than type, so distribute proportionally to room.
    text_take = int(round(take * text_room / total_room))
    type_take = take - text_take
    result: dict[int, int] = {}
    if text_size:
        result[text_idx] = text_size - text_take
    if type_size:
        result[type_idx] = type_size - type_take
    return result
