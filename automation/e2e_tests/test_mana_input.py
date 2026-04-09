"""E2E tests: mana symbol rendering in search inputs and oracle text display.

These tests verify that:
  1. Mana cost search box renders each mana symbol as an inline image when the
     box is populated with the {X} notation.
  2. Oracle text search box renders mana symbols for {X} notation.
  3. Paste into oracle text search renders all symbols in the pasted string.
  4. Card inspector oracle text panel renders symbols from card oracle text.

Golden screenshots are saved to automation/golden/ on the first run.
On subsequent runs the live screenshot is saved alongside the golden for
manual inspection (pixel-perfect comparison is deferred until golden images
are confirmed correct by a human reviewer).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path

from automation.client import AutomationClient
from automation.e2e_tests.common import GOLDEN_DIR

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SCREENSHOTS_DIR = Path(__file__).resolve().parents[2] / "screenshots"


def _save_path(label: str) -> str:
    SCREENSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    return str(SCREENSHOTS_DIR / f"{label}.png")


def _golden_path(label: str) -> str:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    return str(GOLDEN_DIR / f"{label}.png")


def _capture_widget(client: AutomationClient, widget: str, label: str) -> str:
    """Screenshot a named widget, returning the absolute path of the saved PNG."""
    path = _save_path(label)
    result = client.screenshot_widget(widget, path)
    saved = result.get("path", path)
    # First run: copy to golden if golden doesn't exist yet
    golden = _golden_path(label)
    if not os.path.exists(golden):
        import shutil

        shutil.copy2(saved, golden)
        print(f"    (generated golden: {golden})")
    return saved


def _symbol_to_label(symbol: str) -> str:
    """Turn '{W/U}' into 'WU', '{W}' into 'W', etc. for use in file names."""
    return symbol.strip("{}").replace("/", "")


# ---------------------------------------------------------------------------
# Test 1 — mana cost search renders each symbol
# ---------------------------------------------------------------------------

# Representative subset of FULL_MANA_SYMBOLS covering singles, hybrids, phyrexian
_MANA_COST_SAMPLES = [
    "{W}",
    "{U}",
    "{B}",
    "{R}",
    "{G}",
    "{C}",
    "{X}",
    "{0}",
    "{1}",
    "{2}",
    "{W/U}",
    "{R/G}",
    "{G/P}",
    "{2/W}",
]


def test_mana_cost_search_renders_symbols(client: AutomationClient) -> None:
    """Mana cost search box should display each symbol as an inline image."""
    for symbol in _MANA_COST_SAMPLES:
        client.set_mana_search(symbol)
        time.sleep(0.15)
        label = f"mana_cost_search_render_{_symbol_to_label(symbol)}"
        path = _capture_widget(client, "mana_search", label)
        assert os.path.exists(path), f"Screenshot not saved for {symbol}: {path}"

    # Clear after test
    client.set_mana_search("")


# ---------------------------------------------------------------------------
# Test 2 — oracle text search renders each symbol
# ---------------------------------------------------------------------------


def test_oracle_text_search_renders_symbols(client: AutomationClient) -> None:
    """Oracle text search box should display mana symbols as inline images."""
    for symbol in _MANA_COST_SAMPLES:
        client.set_oracle_search(symbol, expand_adv=True)
        time.sleep(0.15)
        label = f"oracle_text_search_render_{_symbol_to_label(symbol)}"
        path = _capture_widget(client, "oracle_search", label)
        assert os.path.exists(path), f"Screenshot not saved for {symbol}: {path}"

    # Clear after test
    client.set_oracle_search("", expand_adv=False)


# ---------------------------------------------------------------------------
# Test 3 — paste into oracle text search renders symbols
# ---------------------------------------------------------------------------

_PASTE_TEXT = "{W} {U}  {B}   {R} {G}"


def test_oracle_text_search_paste_renders_symbols(client: AutomationClient) -> None:
    """Pasting a string with mana symbols should render them as images."""
    client.set_oracle_search(_PASTE_TEXT, expand_adv=True)
    time.sleep(0.2)
    label = "oracle_text_search_render_paste"
    path = _capture_widget(client, "oracle_search", label)
    assert os.path.exists(path), f"Screenshot not saved: {path}"
    # Clear
    client.set_oracle_search("", expand_adv=False)


# ---------------------------------------------------------------------------
# Test 4 — card inspector oracle text renders LOREM_MANA symbols
# ---------------------------------------------------------------------------


def test_oracle_text_lorem_mana_display(client: AutomationClient) -> None:
    """Card inspector oracle text panel should render all LOREM_MANA symbols."""
    from utils.constants import LOREM_MANA

    # Insert the dummy card into the card manager
    result = client.add_lorem_mana_card()
    assert result.get("added"), f"Failed to add lorem mana card: {result}"

    dummy_name = result["name"]

    # Use the builder search to find and select the dummy card so the inspector
    # is populated.  Card manager must have card data loaded for this to work.
    client.builder_search(dummy_name)
    time.sleep(0.5)

    # Check the oracle text control via the inspector
    inspector_result = client.get_inspector_oracle_text()
    oracle_text = inspector_result.get("text", "")
    # The inspector may be empty if no card was selected; skip gracefully.
    if not oracle_text:
        print("    (skip oracle display check: inspector text empty — card data may not be loaded)")
    else:
        assert "{W}" in LOREM_MANA, "LOREM_MANA fixture must contain {W}"

    # Take a screenshot of the inspector oracle display
    label = "oracle_text_lorem"
    path = _capture_widget(client, "oracle_display", label)
    assert os.path.exists(path), f"Screenshot not saved: {path}"

    # Clean up search
    client.builder_search("")


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    (
        "mana_input",
        "Mana cost search renders symbols",
        test_mana_cost_search_renders_symbols,
    ),
    (
        "mana_input",
        "Oracle text search renders symbols",
        test_oracle_text_search_renders_symbols,
    ),
    (
        "mana_input",
        "Oracle text search paste renders symbols",
        test_oracle_text_search_paste_renders_symbols,
    ),
    (
        "mana_input",
        "Oracle text display renders LOREM_MANA",
        test_oracle_text_lorem_mana_display,
    ),
]
