"""E2E tests: deck workspace (builder) — add/subtract cards, roundtrip."""

from __future__ import annotations

from collections.abc import Callable

from automation.client import AutomationClient
from automation.e2e_tests.common import load_dummy_deck

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_builder_add_to_mainboard(client: AutomationClient) -> None:
    """Adding a card to mainboard via add_card_to_zone should increase the count.

    Reproduces the sequence: add_card_to_zone main "Lightning Bolt" → verify count.
    """
    load_dummy_deck(client)
    before = client.get_zone_cards("main")
    initial_total = before["total_qty"]

    client.add_card_to_zone("main", "Lightning Bolt", 1)

    after = client.get_zone_cards("main")
    assert (
        after["total_qty"] == initial_total + 1
    ), f"Expected mainboard total {initial_total + 1}, got {after['total_qty']}"
    bolt = next((c for c in after["cards"] if c["name"] == "Lightning Bolt"), None)
    assert bolt is not None, "Lightning Bolt should be in mainboard"
    assert bolt["qty"] == 5, f"Expected Lightning Bolt qty=5, got {bolt['qty']}"


def test_builder_add_to_sideboard(client: AutomationClient) -> None:
    """Adding a card to sideboard via add_card_to_zone should increase the count.

    Reproduces the sequence: add_card_to_zone side "Rest in Peace" → verify count.
    """
    load_dummy_deck(client)
    before = client.get_zone_cards("side")
    initial_total = before["total_qty"]

    client.add_card_to_zone("side", "Rest in Peace", 1)

    after = client.get_zone_cards("side")
    assert (
        after["total_qty"] == initial_total + 1
    ), f"Expected sideboard total {initial_total + 1}, got {after['total_qty']}"
    rip = next((c for c in after["cards"] if c["name"] == "Rest in Peace"), None)
    assert rip is not None, "Rest in Peace should be in sideboard"
    assert rip["qty"] == 5, f"Expected Rest in Peace qty=5, got {rip['qty']}"


def test_subtract_card_from_mainboard(client: AutomationClient) -> None:
    """Subtracting a card from the mainboard should decrease the count.

    Reproduces the sequence used to fix the subtract button:
    load deck → subtract_card_from_zone main "Goblin Guide" → verify count decreased.
    """
    load_dummy_deck(client)
    before = client.get_zone_cards("main")
    initial_total = before["total_qty"]

    client.subtract_card_from_zone("main", "Goblin Guide", 1)

    after = client.get_zone_cards("main")
    assert (
        after["total_qty"] == initial_total - 1
    ), f"Expected mainboard total {initial_total - 1}, got {after['total_qty']}"
    guide = next((c for c in after["cards"] if c["name"] == "Goblin Guide"), None)
    assert guide is not None, "Goblin Guide should still be in mainboard"
    assert guide["qty"] == 3, f"Expected Goblin Guide qty=3, got {guide['qty']}"


def test_subtract_card_from_sideboard(client: AutomationClient) -> None:
    """Subtracting a card from the sideboard should decrease the count."""
    load_dummy_deck(client)
    before = client.get_zone_cards("side")
    initial_total = before["total_qty"]

    client.subtract_card_from_zone("side", "Smash to Smithereens", 1)

    after = client.get_zone_cards("side")
    assert (
        after["total_qty"] == initial_total - 1
    ), f"Expected sideboard total {initial_total - 1}, got {after['total_qty']}"
    smash = next((c for c in after["cards"] if c["name"] == "Smash to Smithereens"), None)
    assert smash is not None, "Smash to Smithereens should still be in sideboard"
    assert smash["qty"] == 2, f"Expected qty=2, got {smash['qty']}"


def test_subtract_to_zero_removes_card(client: AutomationClient) -> None:
    """Subtracting all copies of a card should remove it from the zone entirely."""
    load_dummy_deck(client)
    # Deflecting Palm has qty=2, subtract both
    client.subtract_card_from_zone("side", "Deflecting Palm", 2)

    after = client.get_zone_cards("side")
    palm = next((c for c in after["cards"] if c["name"] == "Deflecting Palm"), None)
    assert palm is None, "Deflecting Palm should be removed from sideboard after subtracting all"


def test_deck_text_roundtrip(client: AutomationClient) -> None:
    """Loading a deck and reading back zone cards should match the input text."""
    load_dummy_deck(client)

    main = client.get_zone_cards("main")
    side = client.get_zone_cards("side")

    assert main["total_qty"] == 60, f"Expected 60 mainboard cards, got {main['total_qty']}"
    assert side["total_qty"] == 15, f"Expected 15 sideboard cards, got {side['total_qty']}"

    main_names = {c["name"] for c in main["cards"]}
    assert "Lightning Bolt" in main_names
    assert "Goblin Guide" in main_names
    assert "Mountain" in main_names

    side_names = {c["name"] for c in side["cards"]}
    assert "Rest in Peace" in side_names
    assert "Smash to Smithereens" in side_names


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("builder", "Add card to mainboard", test_builder_add_to_mainboard),
    ("builder", "Add card to sideboard", test_builder_add_to_sideboard),
    ("builder", "Subtract card from mainboard", test_subtract_card_from_mainboard),
    ("builder", "Subtract card from sideboard", test_subtract_card_from_sideboard),
    ("builder", "Subtract to zero removes card", test_subtract_to_zero_removes_card),
    ("builder", "Deck text roundtrip", test_deck_text_roundtrip),
]
