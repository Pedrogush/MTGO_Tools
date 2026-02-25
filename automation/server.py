"""
Automation server for receiving and executing commands from the CLI.

The server runs in a background thread and uses wx.CallAfter to execute
commands on the main UI thread.
"""

import json
import socket
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

if TYPE_CHECKING:
    from widgets.app_frame import AppFrame

DEFAULT_PORT = 19847
BUFFER_SIZE = 65536


class AutomationServer:
    """Socket server for receiving automation commands."""

    def __init__(self, frame: "AppFrame", port: int = DEFAULT_PORT):
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
        }

    def register_handler(self, command: str, handler: Callable[..., Any]) -> None:
        """Register a custom command handler."""
        self._command_handlers[command] = handler

    def start(self) -> None:
        """Start the automation server in a background thread."""
        if self._running:
            logger.warning("Automation server already running")
            return

        self._running = True
        self._thread = threading.Thread(target=self._server_loop, daemon=True)
        self._thread.start()
        logger.info(f"Automation server started on port {self.port}")

    def stop(self) -> None:
        """Stop the automation server."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("Automation server stopped")

    def _server_loop(self) -> None:
        """Main server loop - runs in background thread."""
        try:
            self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server_socket.bind(("127.0.0.1", self.port))
            self._server_socket.listen(5)
            self._server_socket.settimeout(1.0)

            while self._running:
                try:
                    client_socket, addr = self._server_socket.accept()
                    logger.debug(f"Client connected from {addr}")
                    self._handle_client(client_socket)
                except TimeoutError:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error(f"Error accepting connection: {e}")
        except Exception as e:
            logger.error(f"Server error: {e}")
        finally:
            if self._server_socket:
                try:
                    self._server_socket.close()
                except Exception:
                    pass

    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            client_socket.settimeout(30.0)
            data = client_socket.recv(BUFFER_SIZE)
            if not data:
                return

            request = json.loads(data.decode("utf-8"))
            response = self._execute_command(request)
            client_socket.sendall(json.dumps(response).encode("utf-8"))
        except json.JSONDecodeError as e:
            response = {"success": False, "error": f"Invalid JSON: {e}"}
            client_socket.sendall(json.dumps(response).encode("utf-8"))
        except Exception as e:
            logger.error(f"Error handling client: {e}")
            try:
                response = {"success": False, "error": str(e)}
                client_socket.sendall(json.dumps(response).encode("utf-8"))
            except Exception:
                pass
        finally:
            try:
                client_socket.close()
            except Exception:
                pass

    def _execute_command(self, request: dict[str, Any]) -> dict[str, Any]:
        """Execute a command and return the result."""
        command = request.get("command", "")
        args = request.get("args", {})

        if command not in self._command_handlers:
            return {"success": False, "error": f"Unknown command: {command}"}

        handler = self._command_handlers[command]

        # Execute on main thread and wait for result
        result_holder: list[dict[str, Any]] = []
        event = threading.Event()

        def run_on_main_thread():
            try:
                result = handler(**args)
                result_holder.append({"success": True, "result": result})
            except Exception as e:
                logger.error(f"Command {command} failed: {e}")
                result_holder.append({"success": False, "error": str(e)})
            finally:
                event.set()

        wx.CallAfter(run_on_main_thread)
        event.wait(timeout=30.0)

        if not result_holder:
            return {"success": False, "error": "Command timed out"}

        return result_holder[0]

    # ------------------------------------------------------------------ Command handlers ------------------------------------------------------------------

    def _handle_ping(self) -> dict[str, Any]:
        """Handle ping command."""
        return {"status": "ok", "timestamp": time.time()}

    def _handle_screenshot(self, path: str | None = None) -> dict[str, Any]:
        """Take a screenshot of the application window."""
        import os
        from datetime import datetime

        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"screenshot_{timestamp}.png"

        # Get the frame's screen position and size
        rect = self.frame.GetScreenRect()
        x, y, width, height = rect.x, rect.y, rect.width, rect.height

        # Create a bitmap to capture the screen
        screen_dc = wx.ScreenDC()
        bmp = wx.Bitmap(width, height)
        mem_dc = wx.MemoryDC(bmp)
        mem_dc.Blit(0, 0, width, height, screen_dc, x, y)
        mem_dc.SelectObject(wx.NullBitmap)

        # Save to file
        image = bmp.ConvertToImage()
        image.SaveFile(path, wx.BITMAP_TYPE_PNG)

        return {"path": os.path.abspath(path), "width": width, "height": height}

    def _handle_get_status(self) -> dict[str, Any]:
        """Get the status bar text."""
        status_text = ""
        if self.frame.status_bar:
            status_text = self.frame.status_bar.GetStatusText()
        return {"status": status_text}

    def _handle_get_window_info(self) -> dict[str, Any]:
        """Get window information."""
        pos = self.frame.GetPosition()
        size = self.frame.GetSize()
        return {
            "title": self.frame.GetTitle(),
            "position": {"x": pos.x, "y": pos.y},
            "size": {"width": size.width, "height": size.height},
            "visible": self.frame.IsShown(),
            "active": self.frame.IsActive(),
        }

    def _handle_list_widgets(self) -> dict[str, Any]:
        """List available widgets and their states."""
        widgets = {}

        # Toolbar buttons
        if hasattr(self.frame, "toolbar"):
            widgets["toolbar"] = {
                "type": "ToolbarButtons",
                "buttons": self._get_button_info(self.frame.toolbar),
            }

        # Research panel
        if self.frame.research_panel:
            widgets["research_panel"] = {
                "type": "DeckResearchPanel",
                "visible": self.frame.research_panel.IsShown(),
            }

        # Builder panel
        if self.frame.builder_panel:
            widgets["builder_panel"] = {
                "type": "DeckBuilderPanel",
                "visible": self.frame.builder_panel.IsShown(),
            }

        # Deck list
        if hasattr(self.frame, "deck_list"):
            widgets["deck_list"] = {
                "type": "DeckResultsList",
                "count": self.frame.deck_list.GetCount(),
            }

        # Deck tabs
        if hasattr(self.frame, "deck_tabs"):
            widgets["deck_tabs"] = {
                "type": "FlatNotebook",
                "page_count": self.frame.deck_tabs.GetPageCount(),
                "current_page": self.frame.deck_tabs.GetSelection(),
            }

        return {"widgets": widgets}

    def _get_button_info(self, parent: wx.Window) -> list[dict[str, Any]]:
        """Get info about buttons in a widget."""
        buttons = []
        for child in parent.GetChildren():
            if isinstance(child, wx.Button):
                buttons.append(
                    {
                        "label": child.GetLabel(),
                        "enabled": child.IsEnabled(),
                        "id": child.GetId(),
                    }
                )
        return buttons

    def _handle_click(self, widget: str, label: str | None = None) -> dict[str, Any]:
        """Click a button by widget name and optional label."""
        target = self._find_widget(widget)
        if target is None:
            return {"clicked": False, "error": f"Widget not found: {widget}"}

        if isinstance(target, wx.Button):
            event = wx.CommandEvent(wx.wxEVT_BUTTON, target.GetId())
            event.SetEventObject(target)
            target.ProcessEvent(event)
            return {"clicked": True, "widget": widget}

        # Search for button by label within the widget
        if label:
            for child in target.GetChildren():
                if isinstance(child, wx.Button) and child.GetLabel() == label:
                    event = wx.CommandEvent(wx.wxEVT_BUTTON, child.GetId())
                    event.SetEventObject(child)
                    child.ProcessEvent(event)
                    return {"clicked": True, "widget": widget, "label": label}

        return {"clicked": False, "error": f"Button not found: {label}"}

    def _find_widget(self, name: str) -> wx.Window | None:
        """Find a widget by name."""
        widget_map = {
            "toolbar": getattr(self.frame, "toolbar", None),
            "research_panel": self.frame.research_panel,
            "builder_panel": self.frame.builder_panel,
            "deck_list": getattr(self.frame, "deck_list", None),
            "deck_tabs": getattr(self.frame, "deck_tabs", None),
            "main_table": getattr(self.frame, "main_table", None),
            "side_table": getattr(self.frame, "side_table", None),
            "card_inspector": getattr(self.frame, "card_inspector_panel", None),
            "copy_button": getattr(self.frame, "copy_button", None),
            "save_button": getattr(self.frame, "save_button", None),
            "daily_average_button": getattr(self.frame, "daily_average_button", None),
        }
        return widget_map.get(name)

    def _handle_set_format(self, format_name: str) -> dict[str, Any]:
        """Set the current format."""
        if self.frame.research_panel:
            research_panel = self.frame.research_panel
            research_panel.format_choice.SetStringSelection(format_name)
            # Trigger the format changed callback (no args needed)
            if hasattr(self.frame, "on_format_changed"):
                self.frame.on_format_changed()
            return {"format": format_name, "set": True}
        return {"set": False, "error": "Research panel not available"}

    def _handle_get_format(self) -> dict[str, Any]:
        """Get the current format."""
        format_name = ""
        if hasattr(self.frame, "controller"):
            format_name = self.frame.controller.current_format
        return {"format": format_name}

    def _handle_get_archetypes(self) -> dict[str, Any]:
        """Get list of archetypes."""
        archetypes = []
        if hasattr(self.frame, "filtered_archetypes"):
            archetypes = [
                {"name": a.get("name", "Unknown"), "url": a.get("url", "")}
                for a in self.frame.filtered_archetypes
            ]
        return {"archetypes": archetypes, "count": len(archetypes)}

    def _handle_select_archetype(
        self, index: int | None = None, name: str | None = None
    ) -> dict[str, Any]:
        """Select an archetype by index or name."""
        if self.frame.research_panel is None:
            return {"selected": False, "error": "Research panel not available"}

        research_panel = self.frame.research_panel

        if name is not None:
            # Find by name
            for i, archetype in enumerate(getattr(self.frame, "filtered_archetypes", [])):
                if archetype.get("name") == name:
                    index = i
                    break
            if index is None:
                return {"selected": False, "error": f"Archetype not found: {name}"}

        if index is not None:
            # Set selection in the list
            research_panel.archetype_list.SetSelection(index)
            # Trigger the selection callback (no args needed)
            if hasattr(self.frame, "on_archetype_selected"):
                self.frame.on_archetype_selected()
            return {"selected": True, "index": index}

        return {"selected": False, "error": "No index or name provided"}

    def _handle_get_deck_list(self) -> dict[str, Any]:
        """Get the list of decks in the deck list."""
        decks = []
        if hasattr(self.frame, "deck_list"):
            for i in range(self.frame.deck_list.GetCount()):
                decks.append(
                    {
                        "index": i,
                        "text": self.frame.deck_list.GetString(i),
                    }
                )
        return {"decks": decks, "count": len(decks)}

    def _handle_select_deck(self, index: int) -> dict[str, Any]:
        """Select a deck by index."""
        if not hasattr(self.frame, "deck_list"):
            return {"selected": False, "error": "Deck list not available"}

        if index < 0 or index >= self.frame.deck_list.GetCount():
            return {"selected": False, "error": f"Invalid index: {index}"}

        self.frame.deck_list.SetSelection(index)
        # Trigger selection event
        event = wx.CommandEvent(wx.wxEVT_LISTBOX, self.frame.deck_list.GetId())
        event.SetInt(index)
        event.SetEventObject(self.frame.deck_list)
        self.frame.deck_list.ProcessEvent(event)
        return {"selected": True, "index": index}

    def _handle_get_deck_text(self) -> dict[str, Any]:
        """Get the current deck text."""
        deck_text = ""
        if hasattr(self.frame, "controller"):
            deck_text = self.frame.controller.deck_repo.get_current_deck_text()
        return {"deck_text": deck_text}

    def _handle_switch_tab(self, tab_name: str) -> dict[str, Any]:
        """Switch to a specific tab in the deck tabs."""
        if not hasattr(self.frame, "deck_tabs"):
            return {"switched": False, "error": "Deck tabs not available"}

        notebook = self.frame.deck_tabs
        for i in range(notebook.GetPageCount()):
            if notebook.GetPageText(i).lower() == tab_name.lower():
                notebook.SetSelection(i)
                return {"switched": True, "tab": tab_name, "index": i}

        return {"switched": False, "error": f"Tab not found: {tab_name}"}

    def _handle_wait(self, ms: int = 1000) -> dict[str, Any]:
        """Wait for a specified number of milliseconds."""
        time.sleep(ms / 1000.0)
        return {"waited": ms}

    def _handle_builder_search(self, card_name: str = "") -> dict[str, Any]:
        """Switch to the deck builder panel and search for a card by name."""
        if not self.frame.builder_panel:
            return {"searched": False, "error": "Builder panel not available"}
        # Switch to builder view
        if hasattr(self.frame, "_show_left_panel"):
            self.frame._show_left_panel("builder", force=True)
        # Set the card name and trigger search
        name_ctrl = self.frame.builder_panel.inputs.get("name")
        if name_ctrl is None:
            return {"searched": False, "error": "Name input not found"}
        name_ctrl.ChangeValue(card_name)
        if hasattr(self.frame, "_on_builder_search"):
            self.frame._on_builder_search()
        return {"searched": True, "card_name": card_name}
