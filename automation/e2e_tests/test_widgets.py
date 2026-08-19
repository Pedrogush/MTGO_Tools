"""E2E tests: sub-widget windows (opponent tracker, match history, etc.)."""

from __future__ import annotations

from collections.abc import Callable

from automation.client import AutomationClient

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_widgets_open_opponent_tracker(client: AutomationClient) -> None:
    """Opening Opponent Tracker leaves the main window up and shows the tracker beside it.

    This assertion is inverted from what it used to be. Until phase 3b of #962,
    ``open_opponent_tracker`` called ``Hide()`` on the main frame while the other
    five companion windows opened alongside it -- review finding F1, and the
    reason the review's first capture pass produced an apparently-blank main
    window. The old expectation was documenting a defect.
    """
    result = client.open_widget("opponent_tracker")
    assert result.get("opened"), f"Expected tracker to open: {result}"

    info = client.get_window_info()
    assert info.get("visible"), "Main window must stay visible while the tracker is open"

    tracker = info.get("tracker_window")
    assert tracker is not None, "Tracker window info missing from get_window_info response"
    w = tracker["size"]["width"]
    h = tracker["size"]["height"]
    assert w >= 360 and h >= 180, f"Tracker window too small: {w}x{h}"


def test_widgets_open_match_history(client: AutomationClient) -> None:
    """The Match History widget should open without crashing."""
    result = client.open_widget("match_history")
    assert "opened" in result or "error" in result, f"open_widget response missing keys: {result}"


def test_widgets_open_every_companion_window(client: AutomationClient) -> None:
    """All six companion windows are reachable by name.

    Two of them (``top_cards``, ``radar``) were not in ``open_widget``'s handler
    map until phase 3b and were reachable only by clicking a toolbar button --
    which stopped existing when the toolbar became a menu bar. Review §5.2.
    """
    for widget in (
        "opponent_tracker",
        "timer_alert",
        "match_history",
        "metagame",
        "top_cards",
        "radar",
    ):
        result = client.open_widget(widget)
        assert result.get("opened"), f"Expected {widget} to open: {result}"
        client.wait(500)


def test_menu_bar_lists_and_activates(client: AutomationClient) -> None:
    """The menu bar replaces ``click toolbar --label ...`` as the harness entry point."""
    listing = client.menu()
    assert listing.get("ok"), f"menu listing failed: {listing}"
    menus = listing["menus"]
    assert len(menus) == 4, f"Expected four menus, got {list(menus)}"
    tools = next(iter(m for name, m in menus.items() if any(
        e["label"].lower().startswith("radar") for e in m
    )), None)
    assert tools is not None, f"No menu offers Radar: {list(menus)}"

    tools_title = next(name for name, m in menus.items() if m is tools)
    opened = client.menu(f"{tools_title}/{tools[-1]['label']}")
    assert opened.get("ok"), f"Activating a menu item failed: {opened}"

    assert not client.menu(f"{tools_title}/No Such Item").get("ok")


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("widgets", "Open Opponent Tracker widget", test_widgets_open_opponent_tracker),
    ("widgets", "Open Match History widget", test_widgets_open_match_history),
    ("widgets", "Every companion window opens by name", test_widgets_open_every_companion_window),
    ("widgets", "Menu bar lists and activates items", test_menu_bar_lists_and_activates),
]
