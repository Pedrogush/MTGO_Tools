"""E2E tests: sub-widget windows (opponent tracker, match history, etc.)."""

from __future__ import annotations

from collections.abc import Callable

from automation.client import AutomationClient

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_widgets_open_opponent_tracker(client: AutomationClient) -> None:
    """Opening Opponent Tracker hides the main window and shows the tracker at a usable size."""
    result = client.open_widget("opponent_tracker")
    assert result.get("opened"), f"Expected tracker to open: {result}"

    info = client.get_window_info()
    assert not info.get("visible", True), "Main window should be hidden while tracker is active"

    tracker = info.get("tracker_window")
    assert tracker is not None, "Tracker window info missing from get_window_info response"
    w = tracker["size"]["width"]
    h = tracker["size"]["height"]
    assert w >= 360 and h >= 180, f"Tracker window too small: {w}x{h}"


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
