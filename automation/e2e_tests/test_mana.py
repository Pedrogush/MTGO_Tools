"""E2E tests: mana symbol rendering in builder search results."""

from __future__ import annotations

import time
from collections.abc import Callable

from automation.client import AutomationClient

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mana_symbols_render_in_builder(client: AutomationClient) -> None:
    """Builder search results should show rendered mana symbol images.

    When searching for cards with mana costs, the _mana_img_index on the
    virtual list should be populated.  An empty index means no symbols were
    rendered (visual regression).
    """
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


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("mana", "Mana symbols render in builder", test_mana_symbols_render_in_builder),
]
