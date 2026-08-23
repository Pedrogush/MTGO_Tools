"""Format detection (rarity for Pauper, legality data otherwise) and archetypes."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager

# MTGO competitive formats in priority order (most → least restrictive card pool).
#
# Pauper is at the end and can never actually be reached from here, because
# every Pauper-legal card is also Legacy- and Vintage-legal: the intersection
# always contains a higher-priority format. That is not a bug in the ordering,
# it is a statement that **legality cannot express Pauper** -- the format is
# defined by rarity. :func:`deck_is_pauper` is the route that does work, and it
# runs before this list is consulted at all. The entry is kept so a card set
# that somehow is legal in Pauper and nowhere else still resolves.
_COMPETITIVE_FORMATS: list[str] = ["standard", "pioneer", "modern", "legacy", "vintage", "pauper"]
_FORMAT_DISPLAY: dict[str, str] = {
    "standard": "Standard",
    "pioneer": "Pioneer",
    "modern": "Modern",
    "legacy": "Legacy",
    "vintage": "Vintage",
    "pauper": "Pauper",
}

#: How many of the cards handed in have to be *recognised* before an all-common
#: card set is called Pauper. Without a floor the rule fires on any short game
#: whose few visible cards happen to be commons -- a Modern deck that cast one
#: Lightning Bolt off basic lands satisfies "every card has a common printing".
#:
#: Five is where the measurement lands (see :func:`deck_is_pauper`): it keeps
#: 100% recall on real Pauper decks at every sample size tested, and holds false
#: positives at 0.00-0.10% of 1,992 non-Pauper decks. Raising it to 8 removes
#: the last false positive but drops recall to 0.9% once only a quarter of a
#: deck is visible, which is the common case in a short match.
_PAUPER_MIN_KNOWN_CARDS = 5


class RarityIndexProto(Protocol):
    """The rarity lookup :func:`deck_is_pauper` needs.

    Structural rather than a concrete import so the gamelog service does not
    depend on the image service's bulk cache to be *type-checked*, and so tests
    can hand in a small real object instead of a mock.
    """

    @property
    def is_loaded(self) -> bool: ...

    def has_common_printing(self, card_name: str) -> bool | None: ...


def deck_is_pauper(
    cards: list[str],
    rarity_index: RarityIndexProto | None = None,
    min_known: int = _PAUPER_MIN_KNOWN_CARDS,
) -> bool:
    """Whether every recognised card in *cards* has a printing at common.

    This is the Pauper test, and it deliberately keys off **rarity** rather than
    legality: Pauper is the one MTGO format whose pool is a rarity filter, so it
    is the one format the legality intersection in
    :func:`_detect_format_via_legalities` structurally cannot name (see the note
    on ``_COMPETITIVE_FORMATS``).

    "Has a printing at common" -- not "is currently common". A card first
    printed at common and reprinted at uncommon still counts, which is what
    makes a per-printing scan necessary; the local card index has no rarity at
    all (see :mod:`services.card_rarity_service`).

    It is *theoretically* possible to build a Legacy or Vintage deck entirely
    out of cards that have common printings, and in practice nobody does -- the
    utility lands and the effects those decks are built around live at uncommon
    and above. Measured against 2,337 real format-labelled decklists (the app's
    own MTGGoldfish archetype/deck caches, joined by format):

    ==================  ==============  ==========================
    cards visible       Pauper recall   false positives (n=1,992)
    ==================  ==============  ==========================
    whole maindeck      345/345 (100%)  0 (0.00%)
    half the deck       345/345 (100%)  0 (0.00%)
    a quarter           345/345 (100%)  5 (0.25%)
    six cards           345/345 (100%)  2 (0.10%)
    ==================  ==============  ==========================

    Unknown names (tokens, mis-parsed log lines) are skipped rather than treated
    as non-common, so one unrecognised string cannot veto the whole verdict.
    Returns ``False`` when no index is available, which leaves the caller on the
    legality path it used before.
    """
    if rarity_index is None or not rarity_index.is_loaded:
        return False

    known = 0
    for card_name in set(cards):
        answer = rarity_index.has_common_printing(card_name)
        if answer is None:
            continue
        if answer is False:
            return False
        known += 1

    return known >= min_known


def detect_format_from_cards(
    cards: list[str],
    card_manager: CardDataManager | None = None,
    last_parsed_format: str = "Unknown",
    rarity_index: RarityIndexProto | None = None,
) -> str:
    """Detect the MTGO format from a card list.

    Two passes, in this order:

    1. :func:`deck_is_pauper` -- a rarity test, because Pauper is invisible to
       the legality intersection below.
    2. the legality intersection -- each card's legal competitive formats
       intersected, returning the most restrictive format covering the whole
       card set.

    Falls back to *last_parsed_format* when neither can decide (e.g. no cards
    with legality data were played).
    """
    if deck_is_pauper(cards, rarity_index):
        return _FORMAT_DISPLAY["pauper"]
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
