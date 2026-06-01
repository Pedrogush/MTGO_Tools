"""Shared ``self`` contract that the :class:`AutomationServer` mixins assume."""

from __future__ import annotations

import socket
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import wx

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame


class AutomationServerProto(Protocol):
    """Cross-mixin ``self`` surface for ``AutomationServer``."""

    frame: AppFrame
    port: int
    _server_socket: socket.socket | None
    _running: bool
    _thread: threading.Thread | None
    _command_handlers: dict[str, Callable[..., Any]]

    # Transport
    def _register_default_handlers(self) -> None: ...
    def _execute_command(self, request: dict[str, Any]) -> dict[str, Any]: ...

    # Screenshot
    def _capture_window_bitmap(self, window: wx.Frame) -> wx.Bitmap: ...
    def _resolve_secondary_window(self, window_name: str) -> wx.Frame | None: ...
    def _find_mana_widget(self, name: str) -> wx.Window | None: ...

    # Introspection
    def _find_widget(self, name: str) -> wx.Window | None: ...
    def _get_button_info(self, parent: wx.Window) -> list[dict[str, Any]]: ...
