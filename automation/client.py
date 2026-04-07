"""
Automation client for sending commands to the running application.
"""

import json
import socket
import time
from typing import Any

from automation.server import BUFFER_SIZE, DEFAULT_PORT


class AutomationError(Exception):
    """Raised when an automation command fails."""

    pass


class ConnectionError(AutomationError):
    """Raised when unable to connect to the automation server."""

    pass


class AutomationClient:
    """Client for sending commands to the automation server."""

    def __init__(self, host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 30.0):
        self.host = host
        self.port = port
        self.timeout = timeout

    def _send_command(self, command: str, **kwargs: Any) -> dict[str, Any]:
        """Send a command to the server and return the response."""
        request = {"command": command, "args": kwargs}

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(self.timeout)
                sock.connect((self.host, self.port))
                sock.sendall(json.dumps(request).encode("utf-8"))
                data = sock.recv(BUFFER_SIZE)
                response = json.loads(data.decode("utf-8"))

                if not response.get("success", False):
                    raise AutomationError(response.get("error", "Unknown error"))

                return response.get("result", {})
        except OSError as e:
            raise ConnectionError(f"Failed to connect to automation server: {e}") from e
        except json.JSONDecodeError as e:
            raise AutomationError(f"Invalid response from server: {e}") from e

    def ping(self) -> dict[str, Any]:
        """Check if the server is responding."""
        return self._send_command("ping")

    def wait_for_server(self, timeout: float = 30.0, interval: float = 0.5) -> bool:
        """Wait for the server to become available."""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                self.ping()
                return True
            except ConnectionError:
                time.sleep(interval)
        return False

    def screenshot(self, path: str | None = None, headless: bool = False) -> dict[str, Any]:
        """Take a screenshot of the application window.

        Args:
            path: Optional path to save the screenshot. If not provided,
                  a timestamped filename will be generated.
            headless: When True, temporarily restores the window if it is
                      minimized so the capture succeeds even when the app
                      is running in the background.

        Returns:
            Dict with 'path', 'width', and 'height' keys.
        """
        kwargs: dict[str, Any] = {}
        if path is not None:
            kwargs["path"] = path
        if headless:
            kwargs["headless"] = True
        return self._send_command("screenshot", **kwargs)

    def get_status(self) -> str:
        """Get the status bar text."""
        result = self._send_command("get_status")
        return result.get("status", "")

    def get_window_info(self) -> dict[str, Any]:
        """Get window information (title, position, size, etc.)."""
        return self._send_command("get_window_info")

    def list_widgets(self) -> dict[str, Any]:
        """List available widgets and their states."""
        return self._send_command("list_widgets")

    def click(self, widget: str, label: str | None = None) -> dict[str, Any]:
        """Click a button by widget name and optional label.

        Args:
            widget: Name of the widget container (e.g., 'toolbar', 'deck_list')
            label: Optional button label to click within the widget

        Returns:
            Dict with 'clicked' boolean and details.
        """
        kwargs = {"widget": widget}
        if label is not None:
            kwargs["label"] = label
        return self._send_command("click", **kwargs)

    def set_format(self, format_name: str) -> dict[str, Any]:
        """Set the current format.

        Args:
            format_name: Name of the format (e.g., 'Modern', 'Standard')
        """
        return self._send_command("set_format", format_name=format_name)

    def get_format(self) -> str:
        """Get the current format."""
        result = self._send_command("get_format")
        return result.get("format", "")

    def get_archetypes(self) -> list[dict[str, str]]:
        """Get list of available archetypes."""
        result = self._send_command("get_archetypes")
        return result.get("archetypes", [])

    def select_archetype(self, index: int | None = None, name: str | None = None) -> dict[str, Any]:
        """Select an archetype by index or name.

        Args:
            index: Index of the archetype to select
            name: Name of the archetype to select (alternative to index)
        """
        kwargs = {}
        if index is not None:
            kwargs["index"] = index
        if name is not None:
            kwargs["name"] = name
        return self._send_command("select_archetype", **kwargs)

    def get_deck_list(self) -> list[dict[str, Any]]:
        """Get the list of decks in the deck results list."""
        result = self._send_command("get_deck_list")
        return result.get("decks", [])

    def select_deck(self, index: int) -> dict[str, Any]:
        """Select a deck by index."""
        return self._send_command("select_deck", index=index)

    def get_deck_text(self) -> str:
        """Get the current deck text."""
        result = self._send_command("get_deck_text")
        return result.get("deck_text", "")

    def switch_tab(self, tab_name: str) -> dict[str, Any]:
        """Switch to a specific tab in the deck workspace.

        Args:
            tab_name: Name of the tab (e.g., 'Deck Tables', 'Stats', 'Sideboard Guide')
        """
        return self._send_command("switch_tab", tab_name=tab_name)

    def wait(self, ms: int = 1000) -> None:
        """Wait for a specified number of milliseconds.

        Args:
            ms: Number of milliseconds to wait
        """
        self._send_command("wait", ms=ms)

    def builder_search(self, card_name: str = "") -> dict[str, Any]:
        """Switch to the deck builder panel and search for a card by name.

        Args:
            card_name: Card name to search for
        """
        return self._send_command("builder_search", card_name=card_name)

    def toggle_adv_filters(self) -> dict[str, Any]:
        """Switch to builder panel and toggle the advanced filters section."""
        return self._send_command("toggle_adv_filters")

    def load_deck_text(self, deck_text: str) -> dict[str, Any]:
        """Load a deck directly from text into the mainboard/sideboard zones.

        Args:
            deck_text: Deck list text in standard format (4 Card Name\\nSideboard\\n2 Other Card)
        """
        return self._send_command("load_deck_text", deck_text=deck_text)

    def get_zone_cards(self, zone: str = "main") -> dict[str, Any]:
        """Get the cards currently in a zone.

        Args:
            zone: 'main', 'side', or 'out'
        """
        return self._send_command("get_zone_cards", zone=zone)

    def add_card_to_zone(self, zone: str, card_name: str, qty: int = 1) -> dict[str, Any]:
        """Add one or more copies of a card to a zone.

        Args:
            zone: 'main' or 'side'
            card_name: Name of the card to add
            qty: Number of copies to add (default 1)
        """
        return self._send_command("add_card_to_zone", zone=zone, card_name=card_name, qty=qty)

    def subtract_card_from_zone(self, zone: str, card_name: str, qty: int = 1) -> dict[str, Any]:
        """Remove one or more copies of a card from a zone.

        Args:
            zone: 'main' or 'side'
            card_name: Name of the card to remove
            qty: Number of copies to remove (default 1)
        """
        return self._send_command(
            "subtract_card_from_zone", zone=zone, card_name=card_name, qty=qty
        )

    def get_scroll_pos(self, zone: str = "main") -> dict[str, Any]:
        """Get the scroll position of a zone's card table.

        Args:
            zone: 'main', 'side', or 'out'
        """
        return self._send_command("get_scroll_pos", zone=zone)

    def get_builder_result_count(self) -> dict[str, Any]:
        """Get the number of search results in the deck builder panel."""
        return self._send_command("get_builder_result_count")

    def get_builder_top_item(self) -> dict[str, Any]:
        """Get the index of the topmost visible item in the builder search results."""
        return self._send_command("get_builder_top_item")

    def scroll_builder_results(self, items: int = 10) -> dict[str, Any]:
        """Scroll the builder results list by the given number of items."""
        return self._send_command("scroll_builder_results", items=items)

    def open_widget(self, widget_name: str) -> dict[str, Any]:
        """Open a top-level widget window.

        Args:
            widget_name: 'opponent_tracker', 'match_history', 'timer_alert', or 'metagame'
        """
        return self._send_command("open_widget", widget_name=widget_name)

    def get_card_images_loaded(self, zone: str = "main") -> dict[str, Any]:
        """Count how many card panels in a zone have loaded card face images.

        Args:
            zone: 'main', 'side', or 'out'
        """
        return self._send_command("get_card_images_loaded", zone=zone)

    def get_deck_notes(self) -> dict[str, Any]:
        """Get the current deck notes and the deck key used to resolve them."""
        return self._send_command("get_deck_notes")

    def set_current_deck(self, deck: dict[str, Any] | None) -> dict[str, Any]:
        """Set the current deck identity used for deck-scoped data."""
        return self._send_command("set_current_deck", deck=deck)

    def close_app(self) -> dict[str, Any]:
        """Close the application.

        Sends a close request to the running app.  The app will shut down
        after acknowledging the command, so the response may arrive just
        before the connection drops.

        Returns:
            Dict with 'closed': True on success.
        """
        return self._send_command("close_app")


def connect(
    host: str = "127.0.0.1", port: int = DEFAULT_PORT, timeout: float = 30.0
) -> AutomationClient:
    """Create and return an automation client.

    Args:
        host: Server host address
        port: Server port
        timeout: Connection timeout in seconds

    Returns:
        Connected AutomationClient instance
    """
    return AutomationClient(host=host, port=port, timeout=timeout)
