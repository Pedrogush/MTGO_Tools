"""E2E tests: golden screenshot capture for visual inspection."""

from __future__ import annotations

import os
import time
from collections.abc import Callable

from automation.client import AutomationClient
from automation.e2e_tests.common import load_dummy_deck, save_screenshot

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_golden_screenshot_dummy_deck(client: AutomationClient) -> None:
    """Load the dummy deck and save a golden screenshot for visual inspection."""
    load_dummy_deck(client)
    time.sleep(0.3)  # Let UI settle

    path = save_screenshot(client, "golden_dummy_deck")
    assert os.path.exists(path), f"Golden screenshot not saved: {path}"
    print(f"    Golden screenshot saved: {path}")


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("golden", "Golden screenshot — dummy deck", test_golden_screenshot_dummy_deck),
]
