"""Format detection (via legality data) and deck archetype classification."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from services.card_data_service import CardDataManager

# MTGO competitive formats in priority order (most → least restrictive card pool)
_COMPETITIVE_FORMATS: list[str] = ["standard", "pioneer", "modern", "legacy", "vintage", "pauper"]
_FORMAT_DISPLAY: dict[str, str] = {
    "standard": "Standard",
    "pioneer": "Pioneer",
    "modern": "Modern",
    "legacy": "Legacy",
    "vintage": "Vintage",
    "pauper": "Pauper",
}


def detect_format_from_cards(
    cards: list[str],
    card_manager: CardDataManager | None = None,
    last_parsed_format: str = "Unknown",
) -> str:
    """Detect the MTGO format from a card list using legality data.

    When *card_manager* is supplied and loaded the function intersects each
    card's legal competitive formats and returns the most restrictive one that
    covers the whole deck.  Falls back to *last_parsed_format* when the format
    cannot be determined (e.g. no cards with legality data were played).
    """
    if card_manager is not None and card_manager.is_loaded:
        return _detect_format_via_legalities(cards, card_manager, last_parsed_format)
    return last_parsed_format


def _detect_format_via_legalities(
    cards: list[str],
    card_manager: CardDataManager,
    last_parsed_format: str = "Unknown",
) -> str:
    legal_format_sets: list[set[str]] = []
    for card_name in set(cards):
        entry = card_manager.get_card(card_name)
        if entry is None:
            continue
        legal = {fmt for fmt in _COMPETITIVE_FORMATS if entry.legalities.get(fmt) == "Legal"}
        if legal:
            legal_format_sets.append(legal)

    if not legal_format_sets:
        return last_parsed_format

    common: set[str] = legal_format_sets[0].copy()
    for s in legal_format_sets[1:]:
        common &= s

    for fmt in _COMPETITIVE_FORMATS:
        if fmt in common:
            return _FORMAT_DISPLAY[fmt]

    return last_parsed_format


def detect_archetype(cards: list[str]) -> str:
    """Detect deck archetype from card list."""
    if not cards or len(cards) < 5:
        return "Unknown"

    card_set = set(cards)

    # Modern archetypes
    archetype_signatures = {
        "Murktide": ["Murktide Regent", "Dragon's Rage Channeler"],
        "Hammer Time": ["Colossus Hammer", "Puresteel Paladin", "Sigarda's Aid"],
        "Tron": ["Urza's Tower", "Urza's Mine", "Urza's Power Plant", "Karn Liberated"],
        "Amulet Titan": ["Amulet of Vigor", "Primeval Titan"],
        "Living End": ["Living End", "Violent Outburst"],
        "Burn": ["Lightning Bolt", "Lava Spike", "Rift Bolt"],
        "Death's Shadow": ["Death's Shadow", "Street Wraith"],
        "Yawgmoth": ["Yawgmoth, Thran Physician", "Chord of Calling"],
        "Scales": ["Hardened Scales", "Walking Ballista", "Arcbound Ravager"],
        "Rhinos": ["Crashing Footfalls", "Shardless Agent"],
        "Scam": ["Grief", "Undying Malice", "Ephemerate"],
        "4C Omnath": ["Omnath, Locus of Creation", "Leyline Binding"],
        "Domain Zoo": ["Leyline Binding", "Scion of Draco"],
        "Elementals": ["Solitude", "Fury", "Risen Reef"],
        "Affinity": ["Cranial Plating", "Ornithopter", "Mox Opal"],
        "Infect": ["Glistener Elf", "Blighted Agent", "Inkmoth Nexus"],
        "Storm": ["Grapeshot", "Gifts Ungiven", "Past in Flames"],
        "Mill": ["Hedron Crab", "Archive Trap", "Visions of Beyond"],
        "Control": ["Teferi, Hero of Dominaria", "Cryptic Command", "Supreme Verdict"],
        "Jund": ["Tarmogoyf", "Dark Confidant", "Liliana of the Veil"],
    }

    # Check signatures (require at least 1 signature card)
    matches = []
    for archetype, signature in archetype_signatures.items():
        signature_matches = sum(1 for card in signature if card in card_set)
        if signature_matches > 0:
            matches.append((archetype, signature_matches, len(signature)))

    # Sort by match count, then by signature size (prefer specific archetypes)
    if matches:
        matches.sort(key=lambda x: (x[1], -x[2]), reverse=True)
        best_match = matches[0]
        if best_match[1] >= 1:  # At least 1 signature card
            return best_match[0]

    # Fallback: generic classification by card types
    lands = sum(
        1
        for card in cards
        if any(x in card for x in ["Plains", "Island", "Swamp", "Mountain", "Forest", "Land"])
    )

    if lands < 10:
        return "Aggro"
    elif lands > 25:
        return "Control"
    else:
        return "Midrange"
