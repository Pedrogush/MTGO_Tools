"""Pure transformation of raw MTGJSON ``data`` into the local index shape.

No I/O, no network — just the normalization rules that turn the upstream
``atomicCards.json`` ``data`` map into ``cards`` / ``cards_by_name`` dicts
ready for msgspec encoding.
"""

from __future__ import annotations

from typing import Any


def build_index(atomic_cards: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    cards: dict[str, dict[str, Any]] = {}
    alias_map: dict[str, dict[str, Any]] = {}
    for variations in atomic_cards.values():
        if not isinstance(variations, list) or not variations:
            continue
        printings = [
            p for p in variations if not p.get("isToken") and p.get("layout") != "token"
        ]
        if not printings:
            continue
        canonical_name = (
            printings[0].get("name") or printings[0].get("faceName") or ""
        ).strip()
        if not canonical_name:
            continue
        front_printing, back_printing = _select_front_back(canonical_name, printings)
        entry = _simplify_printing(front_printing, canonical_name)
        if back_printing is not None:
            _apply_back_face(entry, back_printing, canonical_name)
        for printing in printings:
            other = {k.lower(): v for k, v in (printing.get("legalities") or {}).items()}
            entry["legalities"] = _merge_legalities(entry.get("legalities"), other)
        aliases = entry.setdefault("aliases", set())
        for printing in printings:
            aliases.update(_collect_name_aliases(canonical_name, printing))
        cards[canonical_name.lower()] = entry
    card_list = sorted(cards.values(), key=lambda c: c["name_lower"])
    for card in card_list:
        alias_set = card.pop("aliases", set()) or set()
        alias_set.add(card["name"])
        cleaned_aliases = sorted({alias.strip() for alias in alias_set if alias})
        card["aliases"] = cleaned_aliases
        for alias in cleaned_aliases:
            alias_map.setdefault(alias.lower(), card)
    return {
        "cards": card_list,
        "cards_by_name": alias_map,
    }


def _select_front_back(
    canonical_name: str,
    printings: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Pick which printing is the front face and which (if any) is the back.

    Uses ``faceName`` matched against the part of ``canonical_name`` before
    ``//``. Falls back to printings order when faceNames are missing.
    """
    if "//" not in canonical_name or len(printings) < 2:
        return printings[0], None
    front_part = canonical_name.split("//", 1)[0].strip().lower()
    front_printing: dict[str, Any] | None = None
    back_printing: dict[str, Any] | None = None
    for printing in printings:
        face_name = (printing.get("faceName") or "").strip().lower()
        if face_name == front_part and front_printing is None:
            front_printing = printing
        elif back_printing is None:
            back_printing = printing
    if front_printing is None:
        front_printing = printings[0]
        if back_printing is None:
            back_printing = printings[1]
    return front_printing, back_printing


def _apply_back_face(
    entry: dict[str, Any],
    printing: dict[str, Any],
    canonical_name: str,
) -> None:
    face_name = (printing.get("faceName") or "").strip()
    if not face_name and "//" in canonical_name:
        parts = [p.strip() for p in canonical_name.split("//", 1)]
        if len(parts) == 2:
            face_name = parts[1]
    entry["back_name"] = face_name or None
    entry["back_mana_cost"] = printing.get("manaCost")
    entry["back_type_line"] = printing.get("type")
    entry["back_oracle_text"] = printing.get("text")
    entry["back_power"] = printing.get("power")
    entry["back_toughness"] = printing.get("toughness")
    entry["back_loyalty"] = printing.get("loyalty")


def _simplify_printing(printing: dict[str, Any], canonical_name: str) -> dict[str, Any]:
    legalities = printing.get("legalities") or {}
    mana_value = printing.get("manaValue")
    if isinstance(mana_value, str):
        try:
            mana_value = float(mana_value)
        except ValueError:
            pass
    return {
        "name": canonical_name,
        "name_lower": canonical_name.lower(),
        "mana_cost": printing.get("manaCost"),
        "mana_value": mana_value,
        "type_line": printing.get("type"),
        "oracle_text": printing.get("text"),
        "power": printing.get("power"),
        "toughness": printing.get("toughness"),
        "loyalty": printing.get("loyalty"),
        "colors": printing.get("colors") or [],
        "color_identity": printing.get("colorIdentity") or [],
        "legalities": {k.lower(): v for k, v in legalities.items()},
        "aliases": set(),
    }


def _collect_name_aliases(canonical_name: str, printing: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    face_name = (printing.get("faceName") or "").strip()
    if face_name:
        aliases.add(face_name)
    if canonical_name:
        aliases.add(canonical_name)
        if "//" in canonical_name:
            for piece in canonical_name.split("//"):
                alias = piece.strip()
                if alias:
                    aliases.add(alias)
    return aliases


def _merge_legalities(
    base: dict[str, Any] | None,
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for source in (base or {}), (incoming or {}):
        for fmt, state in source.items():
            if state == "Legal":
                merged[fmt] = state
    return merged


__all__ = ["build_index"]
