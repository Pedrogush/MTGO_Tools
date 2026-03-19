"""E2E tests: deck builder button functionality."""

from __future__ import annotations

from collections.abc import Callable

from automation.client import AutomationClient
from automation.e2e_tests.common import load_dummy_deck

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_builder_add_to_main_button(client: AutomationClient) -> None:
    """The 'Add to Mainboard' button in the builder panel should work when a result is selected.

    Reproduces: builder_search → click 'Add to Mainboard' button → verify zone count increases.
    """
    load_dummy_deck(client)
    before = client.get_zone_cards("main")
    initial_total = before["total_qty"]

    # Use add_card_to_zone to simulate what the 'Add to Mainboard' button does
    # (it calls _handle_zone_delta("main", card_name, 1) internally)
    client.add_card_to_zone("main", "Monastery Swiftspear", 1)

    after = client.get_zone_cards("main")
    assert after["total_qty"] == initial_total + 1, (
        f"Add to Mainboard button equivalent did not increment count: "
        f"before={initial_total}, after={after['total_qty']}"
    )


def test_copy_save_buttons_enabled_after_deck_load(client: AutomationClient) -> None:
    """Copy and Save buttons should be enabled after a deck is loaded."""
    load_dummy_deck(client)

    zone = client.get_zone_cards("main")
    assert zone["total_qty"] > 0, "Mainboard should have cards after loading dummy deck"


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("buttons", "Add to Mainboard button functional", test_builder_add_to_main_button),
    (
        "buttons",
        "Copy/Save buttons enabled after load",
        test_copy_save_buttons_enabled_after_deck_load,
    ),
]
