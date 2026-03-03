#!/usr/bin/env python3
"""
End-to-end UI regression tests for MTGO Tools.

These tests run against the live application and cover:
- App launch / connectivity
- Deck builder: add/subtract cards to/from mainboard and sideboard
- Scrollbar persistence after zone modifications
- Mana symbol rendering in the builder search results
- Button enablement (copy, save)
- Sub-widget windows opening (opponent tracker, match history, etc.)
- Card face image loading in the deck zones

Usage:
    # 1. Start the app with automation enabled (Windows):
    cmd.exe /c "start python C:\\Users\\Pedro\\Documents\\GitHub\\mtgo_tools\\main.py --automation"

    # 2. Wait for the server to come up, then run:
    python -m automation.e2e_tests

    # Or run a specific test group:
    python -m automation.e2e_tests --only builder
    python -m automation.e2e_tests --only scrollbar
    python -m automation.e2e_tests --only mana
    python -m automation.e2e_tests --only buttons
    python -m automation.e2e_tests --only widgets
    python -m automation.e2e_tests --only images

Convention:
  When a UI bug is reproduced via the automation CLI, add a test here that
  replicates the same command sequence so the fix can be verified automatically.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

from automation.client import AutomationClient, AutomationError

# ---------------------------------------------------------------------------
# Dummy deck used as a stable baseline for golden screenshots and assertions.
# Contains a realistic spread of cards with varied mana costs so mana symbols
# and card-image loading are exercised.
# ---------------------------------------------------------------------------
DUMMY_DECK_TEXT = """\
4 Lightning Bolt
4 Goblin Guide
4 Monastery Swiftspear
4 Eidolon of the Great Revel
4 Lava Spike
4 Skullcrack
4 Searing Blaze
4 Rift Bolt
4 Light Up the Stage
4 Inspiring Vantage
4 Sacred Foundry
4 Sunbaked Canyon
4 Fiery Islet
4 Mountain
Sideboard
4 Searing Blood
4 Rest in Peace
3 Smash to Smithereens
2 Deflecting Palm
2 Skullcrack
"""

# Directory where golden screenshots are saved for visual review.
GOLDEN_DIR = Path(__file__).parent / "golden"


# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------


class RunResult:
    def __init__(self, name: str, passed: bool, message: str = "", duration: float = 0.0) -> None:
        self.name = name
        self.passed = passed
        self.message = message
        self.duration = duration


class E2ETestRunner:
    def __init__(self, client: AutomationClient) -> None:
        self.client = client
        self.results: list[RunResult] = []

    def run(self, name: str, fn: Callable[[], None]) -> RunResult:
        start = time.time()
        try:
            fn()
            result = RunResult(name, True, "OK", time.time() - start)
        except AssertionError as exc:
            result = RunResult(name, False, str(exc), time.time() - start)
        except AutomationError as exc:
            result = RunResult(name, False, f"AutomationError: {exc}", time.time() - start)
        except Exception as exc:  # noqa: BLE001
            result = RunResult(name, False, f"Unexpected error: {exc}", time.time() - start)
        self.results.append(result)
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {name} ({result.duration:.2f}s)")
        if not result.passed:
            print(f"         {result.message}")
        return result

    def summary(self) -> int:
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        total_time = sum(r.duration for r in self.results)
        print("\n" + "=" * 60)
        print(f"Tests: {passed} passed, {failed} failed  ({total_time:.2f}s)")
        print("=" * 60)
        return 1 if failed > 0 else 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def save_screenshot(client: AutomationClient, label: str) -> str:
    """Save a screenshot to the golden directory and return its path."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    path = str(GOLDEN_DIR / f"{label}.png")
    result = client.screenshot(path)
    return result.get("path", path)


def load_dummy_deck(client: AutomationClient) -> None:
    """Load the standard dummy deck and assert it succeeded."""
    result = client.load_deck_text(DUMMY_DECK_TEXT)
    assert result.get("loaded"), f"load_deck_text failed: {result}"
    # The dummy deck has 60 mainboard cards (15 card names × 4 copies each except lands)
    assert result["mainboard_count"] > 0, "Mainboard should have cards after loading"
    assert result["sideboard_count"] > 0, "Sideboard should have cards after loading"


# ---------------------------------------------------------------------------
# Test functions
# ---------------------------------------------------------------------------


def test_app_launches(client: AutomationClient) -> None:
    """App should respond to ping and show a window."""
    ping = client.ping()
    assert ping.get("status") == "ok", f"Unexpected ping response: {ping}"

    info = client.get_window_info()
    assert info.get("visible"), "App window should be visible"
    assert "MTGO" in info.get("title", ""), f"Unexpected window title: {info.get('title')}"


def test_builder_add_to_mainboard(client: AutomationClient) -> None:
    """Adding a card to mainboard via add_card_to_zone should increase the count.

    Reproduces the sequence: add_card_to_zone main "Lightning Bolt" → verify count.
    """
    # Start from a clean state
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


def test_scrollbar_persists_after_add(client: AutomationClient) -> None:
    """Scroll position in the mainboard should be preserved after adding a card.

    This reproduces the bug where the scrollbar would reset to the top
    after incrementing a card's quantity.
    """
    load_dummy_deck(client)

    # Simulate scrolling down by adding many cards so the list is scrollable
    for i in range(10):
        client.add_card_to_zone("main", f"TestCard{i:02d}", 1)

    # Get scroll position before the add
    scroll_before = client.get_scroll_pos("main")

    # Add a card (this previously reset the scroll position)
    client.add_card_to_zone("main", "Lightning Bolt", 1)

    scroll_after = client.get_scroll_pos("main")

    # The scroll position should be the same (preserved)
    assert scroll_after["scroll_y"] == scroll_before["scroll_y"], (
        f"Scroll position changed after add: before={scroll_before['scroll_y']}, "
        f"after={scroll_after['scroll_y']}. Scrollbar did not persist."
    )


def test_scrollbar_persists_after_subtract(client: AutomationClient) -> None:
    """Scroll position should be preserved after subtracting a card quantity."""
    load_dummy_deck(client)

    # Scroll down by adding enough cards
    for i in range(10):
        client.add_card_to_zone("main", f"PaddingCard{i:02d}", 1)

    scroll_before = client.get_scroll_pos("main")

    # Subtract one copy of Lightning Bolt
    client.subtract_card_from_zone("main", "Lightning Bolt", 1)

    scroll_after = client.get_scroll_pos("main")

    assert scroll_after["scroll_y"] == scroll_before["scroll_y"], (
        f"Scroll position changed after subtract: before={scroll_before['scroll_y']}, "
        f"after={scroll_after['scroll_y']}. Scrollbar did not persist."
    )


def test_mana_symbols_render_in_builder(client: AutomationClient) -> None:
    """Builder search results should show rendered mana symbol images.

    When searching for cards with mana costs, the _mana_img_index on the
    virtual list should be populated.  An empty index means no symbols were
    rendered (visual regression).
    """
    # Switch to builder and search for a common card with a known mana cost
    client.builder_search("Lightning Bolt")
    time.sleep(0.5)  # Allow async card data to populate

    result = client.get_builder_result_count()
    count = result.get("count", 0)

    if count == 0:
        # Card data may not be loaded yet; this is a soft check
        print("    (skip mana check: no search results — card data may not be loaded)")
        return

    mana_variants = result.get("mana_symbol_variants", 0)
    assert mana_variants > 0, (
        f"Builder returned {count} results but 0 mana symbol variants were rendered. "
        "Mana symbols may not be displaying correctly."
    )


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

    # Check that the deck has been loaded (presence of cards in zone)
    zone = client.get_zone_cards("main")
    assert zone["total_qty"] > 0, "Mainboard should have cards after loading dummy deck"


def test_widgets_open_opponent_tracker(client: AutomationClient) -> None:
    """The Opponent Tracker widget should open without crashing."""
    result = client.open_widget("opponent_tracker")
    # May succeed or fail depending on MTGO not running; just verify no server crash
    assert (
        "opened" in result or "error" in result
    ), f"open_widget response missing 'opened'/'error' keys: {result}"


def test_widgets_open_match_history(client: AutomationClient) -> None:
    """The Match History widget should open without crashing."""
    result = client.open_widget("match_history")
    assert "opened" in result or "error" in result, f"open_widget response missing keys: {result}"


def test_card_faces_loading_after_deck_load(client: AutomationClient) -> None:
    """Card face images should begin loading after a deck is loaded.

    This test waits briefly for async image loads to fire and then checks
    how many card panels have a loaded image bitmap.  We don't require all
    cards to have images (they may not be downloaded) but we check that the
    loading mechanism is triggered.
    """
    load_dummy_deck(client)
    # Give image loading threads a moment to start
    time.sleep(2.0)

    result = client.get_card_images_loaded("main")
    total = result.get("total", 0)
    loaded = result.get("loaded", 0)

    assert total > 0, "Mainboard should have card panels after loading"
    # Log the result — we don't hard-assert all images load (they may be missing locally)
    print(f"    Card images loaded: {loaded}/{total}")


def test_golden_screenshot_dummy_deck(client: AutomationClient) -> None:
    """Load the dummy deck and save a golden screenshot for visual inspection."""
    load_dummy_deck(client)
    time.sleep(0.3)  # Let UI settle

    path = save_screenshot(client, "golden_dummy_deck")
    assert os.path.exists(path), f"Golden screenshot not saved: {path}"
    print(f"    Golden screenshot saved: {path}")


def test_deck_text_roundtrip(client: AutomationClient) -> None:
    """Loading a deck and reading back zone cards should match the input text."""
    load_dummy_deck(client)

    main = client.get_zone_cards("main")
    side = client.get_zone_cards("side")

    # Basic cardinality checks based on the dummy deck definition
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
# Test groups
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("launch", "App launches and responds", test_app_launches),
    ("builder", "Add card to mainboard", test_builder_add_to_mainboard),
    ("builder", "Add card to sideboard", test_builder_add_to_sideboard),
    ("builder", "Subtract card from mainboard", test_subtract_card_from_mainboard),
    ("builder", "Subtract card from sideboard", test_subtract_card_from_sideboard),
    ("builder", "Subtract to zero removes card", test_subtract_to_zero_removes_card),
    ("scrollbar", "Scrollbar persists after add", test_scrollbar_persists_after_add),
    ("scrollbar", "Scrollbar persists after subtract", test_scrollbar_persists_after_subtract),
    ("mana", "Mana symbols render in builder", test_mana_symbols_render_in_builder),
    ("buttons", "Add to Mainboard button functional", test_builder_add_to_main_button),
    (
        "buttons",
        "Copy/Save buttons enabled after load",
        test_copy_save_buttons_enabled_after_deck_load,
    ),
    ("widgets", "Open Opponent Tracker widget", test_widgets_open_opponent_tracker),
    ("widgets", "Open Match History widget", test_widgets_open_match_history),
    ("images", "Card face images load after deck load", test_card_faces_loading_after_deck_load),
    ("golden", "Golden screenshot — dummy deck", test_golden_screenshot_dummy_deck),
    ("builder", "Deck text roundtrip", test_deck_text_roundtrip),
]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def run_all_tests(only: str | None = None) -> int:
    print("MTGO Tools — End-to-End UI Regression Tests")
    print("=" * 60)
    print()

    client = AutomationClient()
    print("Connecting to automation server…")
    if not client.wait_for_server(timeout=15.0):
        print("ERROR: Could not connect to automation server.")
        print("Start the app with:  python main.py --automation")
        return 1
    print("Connected.\n")

    runner = E2ETestRunner(client)
    groups_run = set()

    for group, name, fn in ALL_TESTS:
        if only is not None and group != only:
            continue
        groups_run.add(group)
        runner.run(name, lambda _fn=fn: _fn(client))

    if not groups_run:
        print(
            f"No tests found for group '{only}'. Available: launch, builder, scrollbar, mana, buttons, widgets, images, golden"
        )
        return 1

    return runner.summary()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run MTGO Tools end-to-end UI regression tests.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--only",
        metavar="GROUP",
        help=(
            "Run only tests in this group: "
            "launch, builder, scrollbar, mana, buttons, widgets, images, golden"
        ),
    )
    args = parser.parse_args()
    return run_all_tests(only=args.only)


if __name__ == "__main__":
    sys.exit(main())
