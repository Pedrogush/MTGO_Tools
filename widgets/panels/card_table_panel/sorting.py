"""Pure sort and grouping helpers for table and pile views.

The functions here are wx-independent so they can be unit-tested cleanly.
They consume two inputs:

* a list of zone-card entries (``{"name": str, "qty": int}``)
* a ``get_metadata`` callable that returns a ``CardEntry``-like object or
  ``dict`` with the usual atomic-card fields (``mana_value``, ``type_line``,
  ``colors``, ``oracle_text``, ``mana_cost``).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

# Public column identifiers for the table view.
COL_QTY = "qty"
COL_MANA = "mana"
COL_NAME = "name"
COL_TYPE = "type"
COL_TEXT = "text"
#: Still a valid *sort* key (and the pile view's colour grouping uses the same
#: helpers), but no longer a displayed column: phase 5 dropped it because for
#: every non-land it is a strict function of the Mana column beside it, and for a
#: land it is the same colourless diamond on every row.
COL_COLOR = "color"

#: Displayed columns, in order. Quantity leads, as it does on a written
#: decklist, and is a right-aligned numeric column of its own rather than a
#: "2x " prefix buried inside the left-aligned card name.
TABLE_COLUMNS: tuple[str, ...] = (COL_QTY, COL_MANA, COL_NAME, COL_TYPE, COL_TEXT)

# WUBRG canonical order for color sorting.
_WUBRG = ("W", "U", "B", "R", "G")
_COLOR_ORDER = {c: i for i, c in enumerate(_WUBRG)}

# Pile sort modes.
PILE_SORT_MV = "mv"
PILE_SORT_COLOR = "color"
PILE_SORT_TYPE = "type"

# Table-view row controls: add / subtract / remove.
TABLE_ACTION_COUNT = 3
TABLE_ACTION_ADD, TABLE_ACTION_SUB, TABLE_ACTION_REMOVE = range(TABLE_ACTION_COUNT)

#: Each glyph's hit target, square. The review measured the drawn glyphs at
#: ~14x14 with ~2px between them; 24 is the usual comfortable-pointer-target
#: floor and is what the row height is now sized against too.
TABLE_ACTION_SLOT_WIDTH = 28
#: Gap between the subtract and remove glyphs. ``x`` deletes the row outright
#: while ``-`` decrements it, and they sat adjacent with a ~2px gap, so a
#: mis-aimed decrement destroyed the row. This is a deliberate separation, not
#: padding.
TABLE_ACTION_DESTRUCTIVE_GAP = 16


def action_slot_bounds(cell_width: int) -> list[tuple[int, int]]:
    """``(x0, x1)`` for each action slot, right-aligned inside ``cell_width``.

    Right-aligned so the controls stay pinned to the row's trailing edge however
    wide the column ends up.
    """
    widths = [TABLE_ACTION_SLOT_WIDTH] * TABLE_ACTION_COUNT
    gaps = [0, 0, TABLE_ACTION_DESTRUCTIVE_GAP]
    total = sum(widths) + sum(gaps)
    x = max(0, cell_width - total)
    bounds = []
    for width, gap in zip(widths, gaps, strict=True):
        x += gap
        bounds.append((x, x + width))
        x += width
    return bounds


def action_slot_at(x_in_cell: int, cell_width: int) -> int | None:
    """Map an x offset inside the actions cell to an action slot index.

    Returns ``None`` for the gap in front of the destructive ``x`` and for the
    dead space to the left of the group, so a click that lands between controls
    does nothing instead of firing the nearest one. That is the point of the
    gap: an unclaimed click beside ``x`` must not delete the row.
    """
    if cell_width <= 0:
        return None
    for index, (start, end) in enumerate(action_slot_bounds(cell_width)):
        if start <= x_in_cell < end:
            return index
    return None


def _meta(get_metadata: Callable[[str], Any], name: str) -> dict[str, Any]:
    """Return metadata for ``name`` as a dict-like object, never None."""
    raw = get_metadata(name)
    if raw is None:
        return {}
    return raw


def card_mana_value(meta: Any) -> float:
    """Numeric mana value, defaulting to 0.0 for cards without one (lands)."""
    value = meta.get("mana_value")
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def card_type_line(meta: Any) -> str:
    return (meta.get("type_line") or "").strip()


def is_land(meta: Any) -> bool:
    return "land" in card_type_line(meta).lower()


def card_colors(meta: Any) -> list[str]:
    raw = meta.get("colors") or []
    if isinstance(raw, str):
        return [raw]
    return [c for c in raw if isinstance(c, str)]


def color_sort_key(meta: Any) -> tuple[int, str]:
    """Sort key that puts WUBRG monocolor cards in canonical order, then
    multicolor (count > 1), then colorless. Within each bucket, fall back to
    a deterministic string representation of the color set.
    """
    colors = card_colors(meta)
    if not colors:
        return (10_000, "")  # colorless after everything
    if len(colors) == 1:
        idx = _COLOR_ORDER.get(colors[0], 9_998)
        return (idx, colors[0])
    return (5_000, "".join(sorted(colors)))


def _type_bucket(meta: Any) -> str:
    """Return the dominant card type bucket for pile grouping."""
    type_line = card_type_line(meta).lower()
    # Order matters: lands first, then creatures, planeswalkers, instants,
    # sorceries, artifacts/enchantments, then everything else.
    for keyword in (
        "land",
        "creature",
        "planeswalker",
        "instant",
        "sorcery",
        "battle",
        "artifact",
        "enchantment",
    ):
        if keyword in type_line:
            return keyword
    return "other"


_TYPE_BUCKET_ORDER = {
    "creature": 0,
    "planeswalker": 1,
    "instant": 2,
    "sorcery": 3,
    "battle": 4,
    "artifact": 5,
    "enchantment": 6,
    "other": 7,
    "land": 8,  # lands grouped at the bottom of type-sorted lists
}


def table_sort_key(column: str, meta: Any, name: str, qty: int = 0) -> tuple[Any, ...]:
    """Sort key for a single card row in the table view.

    Lands are grouped at the bottom of the mana-cost sort because their
    nominal mana value of 0 would otherwise put them at the top.
    """
    if column == COL_QTY:
        return (-qty, name.lower())
    if column == COL_MANA:
        return (1 if is_land(meta) else 0, card_mana_value(meta), name.lower())
    if column == COL_NAME:
        return (name.lower(),)
    if column == COL_TYPE:
        return (
            _TYPE_BUCKET_ORDER.get(_type_bucket(meta), 99),
            card_type_line(meta).lower(),
            name.lower(),
        )
    if column == COL_TEXT:
        return ((meta.get("oracle_text") or "").lower(), name.lower())
    if column == COL_COLOR:
        return (*color_sort_key(meta), name.lower())
    return (name.lower(),)


def sort_table_rows(
    cards: list[dict[str, Any]],
    get_metadata: Callable[[str], Any],
    column: str,
    descending: bool = False,
) -> list[dict[str, Any]]:
    """Return ``cards`` sorted by the chosen ``column``."""
    return sorted(
        cards,
        key=lambda c: table_sort_key(
            column, _meta(get_metadata, c["name"]), c["name"], int(c.get("qty", 0) or 0)
        ),
        reverse=descending,
    )


def pile_key_for(card: dict[str, Any], meta: Any, sort_mode: str) -> tuple[int, str]:
    """Return the pile bucket key for a card under ``sort_mode``.

    The first element of the tuple controls the order of piles left-to-right,
    the second is a human-readable label.
    """
    if sort_mode == PILE_SORT_COLOR:
        order, label = color_sort_key(meta)
        readable = _color_label(label)
        return (order, readable)
    if sort_mode == PILE_SORT_TYPE:
        bucket = _type_bucket(meta)
        return (_TYPE_BUCKET_ORDER.get(bucket, 99), bucket.capitalize())
    # default: mana value with lands grouped to the right
    if is_land(meta):
        return (99, "Lands")
    mv = int(card_mana_value(meta))
    label = f"{mv}" if mv < 7 else "7+"
    bucket = min(mv, 7)
    return (bucket, label)


def _color_label(token: str) -> str:
    if not token:
        return "Colorless"
    names = {"W": "White", "U": "Blue", "B": "Black", "R": "Red", "G": "Green"}
    if len(token) == 1:
        return names.get(token, token)
    return "Multicolor"


def group_into_piles(
    cards: Iterable[dict[str, Any]],
    get_metadata: Callable[[str], Any],
    sort_mode: str = PILE_SORT_MV,
) -> list[tuple[tuple[int, str], list[dict[str, Any]]]]:
    """Group ``cards`` into piles, expanding by quantity.

    Each pile is ``((order, label), [card_dict, ...])``. Card dicts inside
    a pile are unique copies (``{"name": str, "qty": 1, "_uid": int}``) so
    selection state can track individual physical copies rather than stacks
    of N.

    The returned list is sorted by ``(order, label)``. Within each pile,
    cards are sorted by mana value then name for a stable visual order.
    """
    expanded: list[tuple[tuple[int, str], dict[str, Any]]] = []
    uid = 0
    for card in cards:
        meta = _meta(get_metadata, card["name"])
        qty = int(card.get("qty") or 0)
        key = pile_key_for(card, meta, sort_mode)
        for _ in range(max(0, qty)):
            uid += 1
            expanded.append((key, {"name": card["name"], "qty": 1, "_uid": uid}))

    piles: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for key, entry in expanded:
        piles.setdefault(key, []).append(entry)

    def _intra_pile_key(entry: dict[str, Any]) -> tuple[float, str]:
        m = _meta(get_metadata, entry["name"])
        return (card_mana_value(m), entry["name"].lower())

    result: list[tuple[tuple[int, str], list[dict[str, Any]]]] = []
    for key in sorted(piles.keys()):
        members = sorted(piles[key], key=_intra_pile_key)
        result.append((key, members))
    return result
