"""Unit tests for the atomic-cards builder's multi-face alias handling."""

from __future__ import annotations

from repositories.card_repository.builder import build_index


def _sample_atomic_payload():
    canonical = "Jace, Vryn's Prodigy // Jace, Telepath Unbound"
    return {
        canonical: [
            {
                "name": canonical,
                "faceName": "Jace, Vryn's Prodigy",
                "manaCost": "{1}{U}",
                "manaValue": 2,
                "type": "Legendary Creature — Human Wizard",
                "text": "T: Draw a card, then discard a card.",
                "power": "0",
                "toughness": "2",
                "colors": ["U"],
                "colorIdentity": ["U"],
                "legalities": {"modern": "Legal"},
            },
            {
                "name": canonical,
                "faceName": "Jace, Telepath Unbound",
                "manaCost": "",
                "manaValue": 0,
                "type": "Legendary Planeswalker — Jace",
                "text": "+1: Up to one target creature gets -2/-0 until your next turn.",
                "loyalty": "5",
                "colors": ["U"],
                "colorIdentity": ["U"],
                "legalities": {"modern": "Legal"},
            },
        ]
    }


def test_build_index_groups_double_faced_cards():
    """Double-faced cards should be indexed once with aliases for each face."""
    index = build_index(_sample_atomic_payload())

    assert len(index["cards"]) == 1
    entry = index["cards"][0]
    assert entry["name"] == "Jace, Vryn's Prodigy // Jace, Telepath Unbound"
    assert set(entry["aliases"]) == {
        "Jace, Vryn's Prodigy // Jace, Telepath Unbound",
        "Jace, Vryn's Prodigy",
        "Jace, Telepath Unbound",
    }
    lookup = index["cards_by_name"]
    cards = index["cards"]
    # ``cards_by_name`` now maps an alias to an index into ``cards`` rather than
    # to a duplicated card object.
    assert cards[lookup["jace, vryn's prodigy"]]["name"] == entry["name"]
    assert cards[lookup["jace, telepath unbound"]]["name"] == entry["name"]


def test_build_index_populates_back_face_fields():
    """Front-face data sits on the canonical fields; back-face on ``back_*``."""
    index = build_index(_sample_atomic_payload())
    entry = index["cards"][0]

    assert entry["type_line"] == "Legendary Creature — Human Wizard"
    assert "Draw a card" in (entry["oracle_text"] or "")
    assert entry["mana_cost"] == "{1}{U}"
    assert entry["mana_value"] == 2
    # Front P/T and colors come from the front printing (not swapped/dropped).
    assert entry["power"] == "0"
    assert entry["toughness"] == "2"
    assert entry["colors"] == ["U"]
    assert entry["color_identity"] == ["U"]

    assert entry["back_name"] == "Jace, Telepath Unbound"
    assert entry["back_type_line"] == "Legendary Planeswalker — Jace"
    assert "+1:" in (entry["back_oracle_text"] or "")
    # Back-face specific fields read from the back printing.
    assert entry["back_mana_cost"] == ""
    assert entry["back_loyalty"] == "5"
    assert entry["back_power"] is None


def test_build_index_back_face_when_back_listed_first():
    """Order of variations should not affect which face is treated as front."""
    canonical = "Jace, Vryn's Prodigy // Jace, Telepath Unbound"
    payload = {
        canonical: [
            {
                "name": canonical,
                "faceName": "Jace, Telepath Unbound",
                "manaCost": "",
                "type": "Legendary Planeswalker — Jace",
                "text": "+1: target creature gets -2/-0.",
                "colors": ["U"],
                "colorIdentity": ["U"],
                "legalities": {"modern": "Legal"},
            },
            {
                "name": canonical,
                "faceName": "Jace, Vryn's Prodigy",
                "manaCost": "{1}{U}",
                "type": "Legendary Creature — Human Wizard",
                "text": "T: Draw a card, then discard a card.",
                "colors": ["U"],
                "colorIdentity": ["U"],
                "legalities": {"modern": "Legal"},
            },
        ]
    }
    index = build_index(payload)
    entry = index["cards"][0]

    assert entry["type_line"] == "Legendary Creature — Human Wizard"
    assert entry["back_type_line"] == "Legendary Planeswalker — Jace"
    assert entry["back_name"] == "Jace, Telepath Unbound"


def test_build_index_single_face_card():
    """The common single-face path should index one card with no back fields."""
    payload = {
        "Lightning Bolt": [
            {
                "name": "Lightning Bolt",
                "manaCost": "{R}",
                "manaValue": 1,
                "type": "Instant",
                "text": "Lightning Bolt deals 3 damage to any target.",
                "colors": ["R"],
                "colorIdentity": ["R"],
                "legalities": {"modern": "Legal"},
            }
        ]
    }
    index = build_index(payload)

    assert len(index["cards"]) == 1
    entry = index["cards"][0]
    assert entry["name"] == "Lightning Bolt"
    # Single-face cards never get back_* fields applied.
    assert "back_name" not in entry
    assert "back_type_line" not in entry
    assert set(entry["aliases"]) == {"Lightning Bolt"}
    assert index["cards_by_name"]["lightning bolt"] == 0


def test_build_index_merges_and_filters_legalities():
    """Only ``Legal`` formats survive, unioned across printings."""
    payload = {
        "Splinter Twin": [
            {
                "name": "Splinter Twin",
                "manaCost": "{2}{R}",
                "manaValue": 3,
                "type": "Enchantment — Aura",
                "legalities": {"modern": "Banned", "legacy": "Legal"},
            },
            {
                "name": "Splinter Twin",
                "manaCost": "{2}{R}",
                "manaValue": 3,
                "type": "Enchantment — Aura",
                "legalities": {"commander": "Legal", "vintage": "Restricted"},
            },
        ]
    }
    index = build_index(payload)
    entry = index["cards"][0]

    # Banned/Restricted dropped; Legal formats from both printings unioned.
    assert entry["legalities"] == {"legacy": "Legal", "commander": "Legal"}


def test_build_index_legalities_union_keeps_legal_across_printings():
    """A format Legal on one printing stays Legal even if Banned on another.

    ``_merge_legalities`` unions the ``Legal`` formats rather than letting a later
    printing's non-Legal state override an earlier Legal one.
    """
    payload = {
        "Format Flip": [
            {
                "name": "Format Flip",
                "manaCost": "{1}",
                "manaValue": 1,
                "type": "Artifact",
                "legalities": {"modern": "Legal", "legacy": "Banned"},
            },
            {
                "name": "Format Flip",
                "manaCost": "{1}",
                "manaValue": 1,
                "type": "Artifact",
                "legalities": {"modern": "Banned", "legacy": "Legal"},
            },
        ]
    }
    index = build_index(payload)
    entry = index["cards"][0]

    # Each format Legal on at least one printing survives the union.
    assert entry["legalities"] == {"modern": "Legal", "legacy": "Legal"}


def test_build_index_sorts_cards_and_maps_distinct_indices():
    """Cards are sorted by name_lower and each alias maps to its own index."""
    payload = {
        "Zealous Conscripts": [
            {
                "name": "Zealous Conscripts",
                "manaCost": "{4}{R}",
                "manaValue": 5,
                "type": "Creature — Human Warrior",
                "legalities": {"modern": "Legal"},
            }
        ],
        "Aether Vial": [
            {
                "name": "Aether Vial",
                "manaCost": "{1}",
                "manaValue": 1,
                "type": "Artifact",
                "legalities": {"modern": "Legal"},
            }
        ],
    }
    index = build_index(payload)
    cards = index["cards"]
    lookup = index["cards_by_name"]

    # Sorted alphabetically by name_lower regardless of input order.
    assert [c["name"] for c in cards] == ["Aether Vial", "Zealous Conscripts"]
    assert lookup["aether vial"] == 0
    assert lookup["zealous conscripts"] == 1
    # Distinct indices resolve back to distinct cards.
    assert cards[lookup["aether vial"]]["name"] == "Aether Vial"
    assert cards[lookup["zealous conscripts"]]["name"] == "Zealous Conscripts"


def test_build_index_filters_token_printings():
    """Token printings are excluded; the remaining real printing is kept."""
    payload = {
        "Soldier": [
            {
                "name": "Soldier",
                "type": "Token Creature — Soldier",
                "isToken": True,
                "legalities": {},
            },
            {
                "name": "Soldier",
                "manaCost": "{1}{W}",
                "manaValue": 2,
                "type": "Creature — Soldier",
                "legalities": {"modern": "Legal"},
            },
        ]
    }
    index = build_index(payload)
    assert len(index["cards"]) == 1
    entry = index["cards"][0]
    assert entry["type_line"] == "Creature — Soldier"
    assert set(entry["aliases"]) == {"Soldier"}


def test_build_index_skips_all_token_groups():
    """A group made up entirely of tokens produces no card."""
    payload = {
        "Treasure": [
            {
                "name": "Treasure",
                "type": "Token Artifact — Treasure",
                "layout": "token",
                "legalities": {},
            }
        ]
    }
    index = build_index(payload)
    assert index["cards"] == []
    assert index["cards_by_name"] == {}


def test_build_index_coerces_numeric_string_mana_value():
    """A numeric-string ``manaValue`` is coerced to float."""
    payload = {
        "Tarmogoyf": [
            {
                "name": "Tarmogoyf",
                "manaCost": "{1}{G}",
                "manaValue": "2",
                "type": "Creature — Lhurgoyf",
                "legalities": {"modern": "Legal"},
            }
        ]
    }
    index = build_index(payload)
    entry = index["cards"][0]
    assert entry["mana_value"] == 2.0
    assert isinstance(entry["mana_value"], float)


def test_build_index_leaves_non_numeric_mana_value_unchanged():
    """A non-numeric-string ``manaValue`` is left as-is (ValueError fallback)."""
    payload = {
        "Mystery Card": [
            {
                "name": "Mystery Card",
                "manaCost": "{X}",
                "manaValue": "unknown",
                "type": "Sorcery",
                "legalities": {"modern": "Legal"},
            }
        ]
    }
    index = build_index(payload)
    entry = index["cards"][0]
    assert entry["mana_value"] == "unknown"


def test_build_index_skips_non_list_and_empty_variations():
    """Group values that are not non-empty lists are ignored."""
    payload = {
        "Bogus String": "not a list",
        "Empty Group": [],
        "Lightning Bolt": [
            {
                "name": "Lightning Bolt",
                "manaCost": "{R}",
                "manaValue": 1,
                "type": "Instant",
                "legalities": {"modern": "Legal"},
            }
        ],
    }
    index = build_index(payload)
    assert [c["name"] for c in index["cards"]] == ["Lightning Bolt"]


def test_build_index_skips_printing_without_name():
    """A printing with neither ``name`` nor ``faceName`` yields no card."""
    payload = {
        "Nameless": [
            {
                "manaCost": "{1}",
                "type": "Artifact",
                "legalities": {"modern": "Legal"},
            }
        ]
    }
    index = build_index(payload)
    assert index["cards"] == []
    assert index["cards_by_name"] == {}


def test_build_index_dfc_without_facenames_derives_back_name_from_canonical():
    """When a DFC printing has no faceName, the back face comes from the second printing.

    With no ``faceName`` to match, ``_select_front_back`` falls back to printings
    order: the first printing is the front and the *second* printing is the back.
    The back name is derived from the half of ``name`` after ``//``.
    """
    canonical = "Front Half // Back Half"
    payload = {
        canonical: [
            {
                "name": canonical,
                "manaCost": "{1}{U}",
                "type": "Creature — Front",
                "text": "Front text.",
                "legalities": {"modern": "Legal"},
            },
            {
                "name": canonical,
                "manaCost": "",
                "type": "Land",
                "text": "Back text.",
                "legalities": {"modern": "Legal"},
            },
        ]
    }
    index = build_index(payload)
    entry = index["cards"][0]

    assert entry["type_line"] == "Creature — Front"
    assert entry["oracle_text"] == "Front text."
    # The back face is the *second* printing, not a re-read of the front.
    assert entry["back_type_line"] == "Land"
    assert entry["back_oracle_text"] == "Back text."
    assert entry["back_mana_cost"] == ""
    # Back name is derived from the canonical's second half when faceName is absent.
    assert entry["back_name"] == "Back Half"
    # Both halves of the canonical are exposed as aliases.
    assert set(entry["aliases"]) == {canonical, "Front Half", "Back Half"}
