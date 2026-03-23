"""E2E tests: deck notes behavior across deck identity changes."""

from __future__ import annotations

from collections.abc import Callable

from automation.client import AutomationClient
from automation.e2e_tests.common import DUMMY_DECK_TEXT


def test_manual_deck_load_resets_deck_key(client: AutomationClient) -> None:
    """Loading a manual deck should resolve notes against the manual deck key."""
    result = client.set_current_deck({"href": "remote-deck", "name": "Remote Deck"})
    assert result["deck_key"] == "remote-deck", f"Unexpected initial deck key: {result}"

    load_result = client.load_deck_text(DUMMY_DECK_TEXT)
    assert load_result.get("loaded"), f"load_deck_text failed: {load_result}"

    notes = client.get_deck_notes()
    assert notes["deck_key"] == "manual", f"Manual deck load kept stale deck key: {notes}"


ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("notes", "Manual deck loads reset deck notes key", test_manual_deck_load_resets_deck_key),
]
