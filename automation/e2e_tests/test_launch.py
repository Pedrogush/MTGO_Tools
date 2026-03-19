"""E2E tests: app launch and connectivity."""

from __future__ import annotations

from collections.abc import Callable

from automation.client import AutomationClient

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_app_launches(client: AutomationClient) -> None:
    """App should respond to ping and show a window."""
    ping = client.ping()
    assert ping.get("status") == "ok", f"Unexpected ping response: {ping}"

    info = client.get_window_info()
    assert info.get("visible"), "App window should be visible"
    assert "MTGO" in info.get("title", ""), f"Unexpected window title: {info.get('title')}"


# ---------------------------------------------------------------------------
# Test group registry
# ---------------------------------------------------------------------------

ALL_TESTS: list[tuple[str, str, Callable[[AutomationClient], None]]] = [
    ("launch", "App launches and responds", test_app_launches),
]
