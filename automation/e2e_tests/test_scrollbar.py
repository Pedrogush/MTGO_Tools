"""E2E tests: scrollbar persistence in deck zones and builder results."""

from __future__ import annotations

import time
from collections.abc import Callable

from automation.client import AutomationClient
from automation.e2e_tests.common import load_dummy_deck

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_scrollbar_persists_after_add(client: AutomationClient) -> None:
    """Scroll position in the mainboard should be preserved after adding a card.

    This reproduces the bug where the scrollbar would reset to the top
    after incrementing a card's quantity.
    """
    load_dummy_deck(client)

    # Simulate scrolling down by adding many cards so the list is scrollable
    for i in range(10):
        client.add_card_to_zone("main", f"TestCard{i:02d}", 1)

    scroll_before = client.get_scroll_pos("main")

    # Add a card (this previously reset the scroll position)
    client.add_card_to_zone("main", "Lightning Bolt", 1)

    scroll_after = client.get_scroll_pos("main")

    assert scroll_after["scroll_y"] == scroll_before["scroll_y"], (
        f"Scroll position changed after add: before={scroll_before['scroll_y']}, "
        f"after={scroll_after['scroll_y']}. Scrollbar did not persist."
    )


def test_scrollbar_persists_after_subtract(client: AutomationClient) -> None:
    """Scroll position should be preserved after subtracting a card quantity."""
    load_dummy_deck(client)

    for i in range(10):
        client.add_card_to_zone("main", f"PaddingCard{i:02d}", 1)

    scroll_before = client.get_scroll_pos("main")

    client.subtract_card_from_zone("main", "Lightning Bolt", 1)

    scroll_after = client.get_scroll_pos("main")

    assert scroll_after["scroll_y"] == scroll_before["scroll_y"], (
        f"Scroll position changed after subtract: before={scroll_before['scroll_y']}, "
        f"after={scroll_after['scroll_y']}. Scrollbar did not persist."
    )


def test_builder_search_scroll_resets(client: AutomationClient) -> None:
    """Builder results should scroll back to the top when the result set shrinks.

    Reproduces issue #233: typing a narrow query (e.g. "Relic of Progenitus") after
    having scrolled down in a broad result set made the single result render off-screen
    near the bottom because the scroll position was not reset on SetData().
    """
    # Broad search — produces many results so the list is scrollable
    client.builder_search("a")
    time.sleep(0.8)  # wait for card data + virtual list to populate

    broad_count = client.get_builder_result_count().get("count", 0)
    if broad_count == 0:
        print("    (skip: no card data loaded — broad search returned 0 results)")
        return

    # Scroll down to simulate a user who scrolled before typing a narrow query
    client.scroll_builder_results(items=30)
    time.sleep(0.1)
    top_after_scroll = client.get_builder_top_item().get("top_item", 0)
    if top_after_scroll == 0:
        print("    (skip: list is not tall enough to scroll — fewer than 30 visible items)")
        return

    # Narrow to a single card that is unlikely to share a name with others
    client.builder_search("Relic of Progenitus")
    time.sleep(0.5)

    top = client.get_builder_top_item().get("top_item", -1)
    assert top == 0, (
        f"After narrowing search results the topmost visible item was {top}, expected 0. "
        "Builder scroll position was not reset when the result set shrank."
    )


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("scrollbar", "Scrollbar persists after add", test_scrollbar_persists_after_add),
    ("scrollbar", "Scrollbar persists after subtract", test_scrollbar_persists_after_subtract),
    (
        "scrollbar",
        "Builder search scroll resets on narrow results",
        test_builder_search_scroll_resets,
    ),
]
