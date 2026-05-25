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
    assert lookup["jace, vryn's prodigy"]["name"] == entry["name"]
    assert lookup["jace, telepath unbound"]["name"] == entry["name"]


def test_build_index_populates_back_face_fields():
    """Front-face data sits on the canonical fields; back-face on ``back_*``."""
    index = build_index(_sample_atomic_payload())
    entry = index["cards"][0]

    assert entry["type_line"] == "Legendary Creature — Human Wizard"
    assert "Draw a card" in (entry["oracle_text"] or "")
    assert entry["mana_cost"] == "{1}{U}"

    assert entry["back_name"] == "Jace, Telepath Unbound"
    assert entry["back_type_line"] == "Legendary Planeswalker — Jace"
    assert "+1:" in (entry["back_oracle_text"] or "")


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
