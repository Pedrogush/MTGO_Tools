"""Automation server package — receives and executes CLI commands.

The server runs in a background thread and uses ``wx.CallAfter`` to execute
commands on the main UI thread.

Split by responsibility into internal modules mirroring
``controllers/app_controller/``:

- ``window_capture``: stateless Win32/ctypes setup + Pillow PNG save helper
  (non-mixin support module)
- ``protocol``: :class:`AutomationServerProto` typing the composed host
- ``transport``: socket transport/lifecycle + handler registry/dispatch
  (``TransportMixin``)
- ``screenshot``: PrintWindow capture + screenshot handlers (``ScreenshotMixin``)
- ``introspection``: ping/status/window-info/click/wait/open/close
  (``IntrospectionMixin``)
- ``deck_research``: format/archetype/deck-list/tab handlers (``DeckResearchMixin``)
- ``zone_editing``: mainboard/sideboard/out zone editing (``ZoneEditingMixin``)
- ``builder``: deck-builder search/filters/scrolling (``BuilderMixin``)
- ``mana_rendering``: mana/oracle search inputs + LOREM_MANA card
  (``ManaRenderingMixin``)

The public import path ``automation.server`` keeps exporting
:class:`AutomationServer`, ``DEFAULT_PORT`` and ``BUFFER_SIZE``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from automation.server.builder import BuilderMixin
from automation.server.deck_research import DeckResearchMixin
from automation.server.introspection import IntrospectionMixin
from automation.server.mana_rendering import ManaRenderingMixin
from automation.server.screenshot import ScreenshotMixin
from automation.server.scroll_perf import ScrollPerfMixin
from automation.server.transport import BUFFER_SIZE, TransportMixin
from automation.server.video import VideoMixin
from automation.server.zone_editing import ZoneEditingMixin

if TYPE_CHECKING:
    import socket
    import threading

    from widgets.frames.app_frame import AppFrame

DEFAULT_PORT = 19847


class AutomationServer(
    TransportMixin,
    ScreenshotMixin,
    IntrospectionMixin,
    DeckResearchMixin,
    ZoneEditingMixin,
    BuilderMixin,
    ManaRenderingMixin,
    ScrollPerfMixin,
    VideoMixin,
):
    """Socket server for receiving automation commands."""

    def __init__(self, frame: AppFrame, port: int = DEFAULT_PORT):
        self.frame = frame
        self.port = port
        self._server_socket: socket.socket | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self._command_handlers: dict[str, Callable[..., Any]] = {}
        self._register_default_handlers()

    def _register_default_handlers(self) -> None:
        """Register built-in command handlers."""
        self._command_handlers = {
            "ping": self._handle_ping,
            "screenshot": self._handle_screenshot,
            "get_status": self._handle_get_status,
            "get_window_info": self._handle_get_window_info,
            "list_widgets": self._handle_list_widgets,
            "click": self._handle_click,
            "set_format": self._handle_set_format,
            "get_format": self._handle_get_format,
            "get_archetypes": self._handle_get_archetypes,
            "select_archetype": self._handle_select_archetype,
            "get_deck_list": self._handle_get_deck_list,
            "select_deck": self._handle_select_deck,
            "get_deck_text": self._handle_get_deck_text,
            "switch_tab": self._handle_switch_tab,
            "wait": self._handle_wait,
            "builder_search": self._handle_builder_search,
            # Zone editing commands
            "load_deck_text": self._handle_load_deck_text,
            "get_zone_cards": self._handle_get_zone_cards,
            "add_card_to_zone": self._handle_add_card_to_zone,
            "subtract_card_from_zone": self._handle_subtract_card_from_zone,
            "get_scroll_pos": self._handle_get_scroll_pos,
            "get_builder_result_count": self._handle_get_builder_result_count,
            "get_builder_top_item": self._handle_get_builder_top_item,
            "scroll_builder_results": self._handle_scroll_builder_results,
            "open_widget": self._handle_open_widget,
            "get_card_images_loaded": self._handle_get_card_images_loaded,
            "get_deck_notes": self._handle_get_deck_notes,
            "set_current_deck": self._handle_set_current_deck,
            "toggle_adv_filters": self._handle_toggle_adv_filters,
            "close_app": self._handle_close_app,
            # Mana symbol rendering commands (issue #410)
            "set_mana_search": self._handle_set_mana_search,
            "set_oracle_search": self._handle_set_oracle_search,
            "screenshot_widget": self._handle_screenshot_widget,
            "screenshot_window": self._handle_screenshot_window,
            "add_lorem_mana_card": self._handle_add_lorem_mana_card,
            "get_inspector_oracle_text": self._handle_get_inspector_oracle_text,
            # Mouse-wheel scroll latency instrumentation
            "wheel_scroll_start": self._handle_wheel_scroll_start,
            "get_scroll_perf": self._handle_get_scroll_perf,
            # Background-thread frame recording (transition capture)
            "start_video": self._handle_start_video,
            "stop_video": self._handle_stop_video,
        }


__all__ = ["AutomationServer", "DEFAULT_PORT", "BUFFER_SIZE"]
