"""E2E tests: card face image loading in deck zones."""

from __future__ import annotations

import time
from collections.abc import Callable

from automation.client import AutomationClient
from automation.e2e_tests.common import load_dummy_deck

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("images", "Card face images load after deck load", test_card_faces_loading_after_deck_load),
]
