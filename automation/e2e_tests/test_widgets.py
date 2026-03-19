"""E2E tests: sub-widget windows (opponent tracker, match history, etc.)."""

from __future__ import annotations

from collections.abc import Callable

from automation.client import AutomationClient

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("widgets", "Open Opponent Tracker widget", test_widgets_open_opponent_tracker),
    ("widgets", "Open Match History widget", test_widgets_open_match_history),
]
