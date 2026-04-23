"""
Automation server for receiving and executing commands from the CLI.

The server runs in a background thread and uses wx.CallAfter to execute
commands on the main UI thread.
"""

import ctypes
import json
import os as _os
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

# Win32 PrintWindow — the only reliable way to capture a wxFrame on Windows
# 10/11, including when the window is occluded by other windows.  A plain
# ScreenDC/Blit captures screen pixels, so any covering window corrupts the
# result.  PrintWindow asks DWM to render the window's own composition
# buffer directly into a supplied HDC.
_PW_RENDERFULLCONTENT = 0x00000002
_user32 = ctypes.windll.user32 if _os.name == "nt" else None  # type: ignore[attr-defined]
if _user32 is not None:
    _user32.PrintWindow.argtypes = [
        ctypes.c_void_p,  # HWND
        ctypes.c_void_p,  # HDC
        ctypes.c_uint,  # flags
    ]
    _user32.PrintWindow.restype = ctypes.c_int


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

    def _handle_screenshot(self, path: str | None = None, headless: bool = False) -> dict[str, Any]:
        """Take a screenshot of the application window.

        Uses the Win32 PrintWindow API (PW_RENDERFULLCONTENT) so the capture
        works even when the window is occluded by other windows.  The *headless*
        parameter is accepted for backward compatibility but is now a no-op —
        PrintWindow is inherently headless.
        """
        import os
        import tempfile
        from datetime import datetime

        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"screenshot_{timestamp}.png"

        # If the requested directory doesn't exist (e.g. /tmp/ passed from WSL),
        # fall back to the system temp directory so SaveFile never shows a dialog.
        save_dir = os.path.dirname(os.path.abspath(path))
        if save_dir and not os.path.isdir(save_dir):
            path = os.path.join(tempfile.gettempdir(), os.path.basename(path))

        bmp = self._capture_window_bitmap(self.frame)
        width, height = bmp.GetWidth(), bmp.GetHeight()

        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        log_null = wx.LogNull()
        ok = bmp.SaveFile(path, wx.BITMAP_TYPE_PNG)
        del log_null
        if not ok:
            raise RuntimeError(f"Failed to save screenshot to {path!r}")

        # Best-effort fsync so the WSL side sees the full file immediately.
        try:
            fd = os.open(path, os.O_RDONLY)
            os.fsync(fd)
            os.close(fd)
        except OSError:
            pass

        return {"path": os.path.abspath(path), "width": width, "height": height}

    def _capture_window_bitmap(self, window: wx.Frame) -> wx.Bitmap:
        """Capture *window* via Win32 PrintWindow and return a wx.Bitmap.

        Works for any wx.Frame — the main AppFrame or any secondary top-level
        window.  Must be called on the wx main thread.  Performs a layout +
        repaint pass and drains the event queue before capturing so DWM has
        finished compositing the window contents.
        """
        if _user32 is None:
            raise RuntimeError("PrintWindow is only available on Windows")

        # DWM cannot composite a minimized (iconized) window — restore it first.
        if window.IsIconized():
            window.Iconize(False)

        # Force a fresh layout and an immediate repaint of the whole widget tree.
        window.Layout()
        window.SendSizeEvent()

        def _refresh_tree(w: wx.Window) -> None:
            w.Refresh(eraseBackground=False)
            w.Update()
            for child in w.GetChildren():
                _refresh_tree(child)

        _refresh_tree(window)

        # Drain the event queue, sleep for DWM composite, then drain again.
        # Values tuned empirically — shorter sleeps produced half-painted captures.
        for _ in range(5):
            wx.Yield()
        time.sleep(0.15)
        for _ in range(3):
            wx.Yield()

        w, h = window.GetSize()
        bmp = wx.Bitmap(w, h, depth=32)
        mdc = wx.MemoryDC(bmp)
        hdc = mdc.GetHDC()
        hwnd = window.GetHandle()
        ok = _user32.PrintWindow(hwnd, hdc, _PW_RENDERFULLCONTENT)
        mdc.SelectObject(wx.NullBitmap)
        if not ok:
            raise RuntimeError("PrintWindow returned 0 (DWM not compositing?)")
        return bmp

    def _resolve_secondary_window(self, window_name: str) -> wx.Frame | None:
        """Return the live wx.Frame for a named secondary window, or None."""
        attr_map = {
            "opponent_tracker": "tracker_window",
            "timer_alert": "timer_window",
            "match_history": "history_window",
            "metagame": "metagame_window",
            "top_cards": "top_cards_window",
            "mana_keyboard": "mana_keyboard_window",
        }
        attr = attr_map.get(window_name)
        if attr is None:
            return None
        window = getattr(self.frame, attr, None)
        if window is None or not window.IsShown():
            return None
        return window

    def _handle_screenshot_window(
        self, window_name: str, path: str | None = None
    ) -> dict[str, Any]:
        """Take a screenshot of a named secondary top-level window.

        Supported window names: opponent_tracker, timer_alert, match_history,
        metagame, top_cards, mana_keyboard.  The window must already be open
        (use open_widget first if needed).
        """
        import os
        import tempfile
        from datetime import datetime

        window = self._resolve_secondary_window(window_name)
        if window is None:
            available = (
                "opponent_tracker, timer_alert, match_history, metagame, top_cards, mana_keyboard"
            )
            return {
                "error": f"Window {window_name!r} not found or not open. Available: {available}"
            }

        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"window_{window_name}_{ts}.png"

        save_dir = os.path.dirname(os.path.abspath(path))
        if save_dir and not os.path.isdir(save_dir):
            path = os.path.join(tempfile.gettempdir(), os.path.basename(path))

        bmp = self._capture_window_bitmap(window)
        width, height = bmp.GetWidth(), bmp.GetHeight()

        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        log_null = wx.LogNull()
        ok = bmp.SaveFile(path, wx.BITMAP_TYPE_PNG)
        del log_null
        if not ok:
            raise RuntimeError(f"Failed to save window screenshot to {path!r}")

        try:
            fd = os.open(path, os.O_RDONLY)
            os.fsync(fd)
            os.close(fd)
        except OSError:
            pass

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
        info: dict[str, Any] = {
            "title": self.frame.GetTitle(),
            "position": {"x": pos.x, "y": pos.y},
            "size": {"width": size.width, "height": size.height},
            "visible": self.frame.IsShown(),
            "active": self.frame.IsActive(),
        }
        tracker = getattr(self.frame, "tracker_window", None)
        if tracker is not None:
            try:
                if tracker.IsShown():
                    t_pos = tracker.GetPosition()
                    t_size = tracker.GetSize()
                    info["tracker_window"] = {
                        "position": {"x": t_pos.x, "y": t_pos.y},
                        "size": {"width": t_size.width, "height": t_size.height},
                        "visible": True,
                    }
            except Exception:
                pass
        return info

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
            # Set selection in the list; +1 because "Any" occupies position 0
            research_panel.archetype_list.SetSelection(index + 1)
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

    def _handle_toggle_adv_filters(self) -> dict[str, Any]:
        """Switch to builder panel and toggle the advanced filters section."""
        if not self.frame.builder_panel:
            return {"toggled": False, "error": "Builder panel not available"}
        if hasattr(self.frame, "_show_left_panel"):
            self.frame._show_left_panel("builder", force=True)
        panel = self.frame.builder_panel
        btn = getattr(panel, "_adv_toggle_btn", None)
        if btn is None:
            return {"toggled": False, "error": "Advanced filters toggle button not found"}
        event = wx.CommandEvent(wx.wxEVT_BUTTON, btn.GetId())
        event.SetEventObject(btn)
        btn.ProcessEvent(event)
        adv_panel = getattr(panel, "_adv_panel", None)
        shown = adv_panel.IsShown() if adv_panel else None
        return {"toggled": True, "expanded": shown}

    def _handle_load_deck_text(self, deck_text: str) -> dict[str, Any]:
        """Load a deck from text into the mainboard/sideboard zones."""
        if not hasattr(self.frame, "_on_deck_content_ready"):
            return {"loaded": False, "error": "Frame does not support _on_deck_content_ready"}
        self.frame._on_deck_content_ready(deck_text, source="automation")
        zone_cards = getattr(self.frame, "zone_cards", {})
        return {
            "loaded": True,
            "mainboard_count": sum(c["qty"] for c in zone_cards.get("main", [])),
            "sideboard_count": sum(c["qty"] for c in zone_cards.get("side", [])),
        }

    def _handle_get_zone_cards(self, zone: str = "main") -> dict[str, Any]:
        """Get the cards in a zone (main, side, or out)."""
        zone_cards = getattr(self.frame, "zone_cards", {})
        cards = zone_cards.get(zone, [])
        return {
            "zone": zone,
            "cards": [{"name": c["name"], "qty": c["qty"]} for c in cards],
            "total_qty": sum(c["qty"] for c in cards),
            "unique_cards": len(cards),
        }

    def _handle_get_deck_notes(self) -> dict[str, Any]:
        """Get the current deck notes cards and resolved deck key."""
        deck_repo = self.frame.controller.deck_repo
        notes_panel = self.frame.deck_notes_panel
        return {
            "deck_key": deck_repo.get_current_deck_key(),
            "notes": notes_panel.get_notes(),
        }

    def _handle_set_current_deck(self, deck: dict[str, Any] | None = None) -> dict[str, Any]:
        """Set the current deck identity used for deck-scoped stores."""
        deck_repo = self.frame.controller.deck_repo
        deck_repo.set_current_deck(deck)
        return {
            "deck_key": deck_repo.get_current_deck_key(),
        }

    def _handle_add_card_to_zone(self, zone: str, card_name: str, qty: int = 1) -> dict[str, Any]:
        """Add a card to a zone by directly calling the zone delta handler."""
        if not hasattr(self.frame, "_handle_zone_delta"):
            return {"added": False, "error": "Frame does not support _handle_zone_delta"}
        self.frame._handle_zone_delta(zone, card_name, qty)
        zone_cards = getattr(self.frame, "zone_cards", {})
        cards = zone_cards.get(zone, [])
        card_entry = next((c for c in cards if c["name"].lower() == card_name.lower()), None)
        return {
            "added": True,
            "zone": zone,
            "card_name": card_name,
            "new_qty": card_entry["qty"] if card_entry else 0,
            "total_qty": sum(c["qty"] for c in cards),
        }

    def _handle_subtract_card_from_zone(
        self, zone: str, card_name: str, qty: int = 1
    ) -> dict[str, Any]:
        """Subtract (decrement) a card from a zone."""
        if not hasattr(self.frame, "_handle_zone_delta"):
            return {"subtracted": False, "error": "Frame does not support _handle_zone_delta"}
        self.frame._handle_zone_delta(zone, card_name, -qty)
        zone_cards = getattr(self.frame, "zone_cards", {})
        cards = zone_cards.get(zone, [])
        card_entry = next((c for c in cards if c["name"].lower() == card_name.lower()), None)
        return {
            "subtracted": True,
            "zone": zone,
            "card_name": card_name,
            "new_qty": card_entry["qty"] if card_entry else 0,
            "total_qty": sum(c["qty"] for c in cards),
        }

    def _handle_get_scroll_pos(self, zone: str = "main") -> dict[str, Any]:
        """Get the scroll position of a zone's scrolled panel."""
        table = None
        if zone == "main":
            table = getattr(self.frame, "main_table", None)
        elif zone == "side":
            table = getattr(self.frame, "side_table", None)
        elif zone == "out":
            table = getattr(self.frame, "out_table", None)

        if table is None:
            return {
                "zone": zone,
                "scroll_x": 0,
                "scroll_y": 0,
                "error": f"No table for zone: {zone}",
            }

        scroller = getattr(table, "scroller", None)
        if scroller is None:
            return {"zone": zone, "scroll_x": 0, "scroll_y": 0, "error": "No scroller on table"}

        x, y = scroller.GetViewStart()
        return {"zone": zone, "scroll_x": x, "scroll_y": y}

    def _handle_get_builder_result_count(self) -> dict[str, Any]:
        """Get the number of results currently shown in the builder search panel."""
        if not self.frame.builder_panel:
            return {"count": 0, "error": "Builder panel not available"}
        results_ctrl = getattr(self.frame.builder_panel, "results_ctrl", None)
        if results_ctrl is None:
            return {"count": 0}
        count = results_ctrl.GetItemCount()
        mana_images = len(getattr(results_ctrl, "_mana_img_index", {}))
        return {"count": count, "mana_symbol_variants": mana_images}

    def _handle_get_builder_top_item(self) -> dict[str, Any]:
        """Get the index of the topmost visible item in the builder search results."""
        if not self.frame.builder_panel:
            return {"top_item": 0, "error": "Builder panel not available"}
        results_ctrl = getattr(self.frame.builder_panel, "results_ctrl", None)
        if results_ctrl is None:
            return {"top_item": 0}
        top = results_ctrl.GetTopItem()
        return {"top_item": top}

    def _handle_scroll_builder_results(self, items: int = 10) -> dict[str, Any]:
        """Scroll the builder results list by the given number of items."""
        if not self.frame.builder_panel:
            return {"scrolled": False, "error": "Builder panel not available"}
        results_ctrl = getattr(self.frame.builder_panel, "results_ctrl", None)
        if results_ctrl is None:
            return {"scrolled": False, "error": "results_ctrl not found"}
        count = results_ctrl.GetItemCount()
        if count == 0:
            return {"scrolled": False, "error": "No items in results list"}
        # Get pixel height of one item from its rect
        rect = results_ctrl.GetItemRect(0)
        item_h = rect.height if rect.height > 0 else 18
        results_ctrl.ScrollList(0, items * item_h)
        return {"scrolled": True, "items": items, "pixels": items * item_h}

    def _handle_open_widget(self, widget_name: str) -> dict[str, Any]:
        """Open a top-level widget window (opponent_tracker, match_history, timer_alert, metagame)."""
        handler_map = {
            "opponent_tracker": "open_opponent_tracker",
            "match_history": "open_match_history",
            "timer_alert": "open_timer_alert",
            "metagame": "open_metagame_analysis",
        }
        method_name = handler_map.get(widget_name)
        if not method_name:
            return {"opened": False, "error": f"Unknown widget: {widget_name}"}
        method = getattr(self.frame, method_name, None)
        if method is None:
            return {"opened": False, "error": f"Method not found: {method_name}"}
        method()
        return {"opened": True, "widget": widget_name}

    def _handle_close_app(self) -> dict[str, Any]:
        """Close the application after sending the response."""
        # Schedule Close on the next event-loop iteration so the response is
        # sent back to the client before the wx app exits.
        wx.CallAfter(self.frame.Close, True)
        return {"closed": True}

    def _handle_get_card_images_loaded(self, zone: str = "main") -> dict[str, Any]:
        """Count how many card panels in a zone have successfully loaded images."""
        table = None
        if zone == "main":
            table = getattr(self.frame, "main_table", None)
        elif zone == "side":
            table = getattr(self.frame, "side_table", None)
        elif zone == "out":
            table = getattr(self.frame, "out_table", None)

        if table is None:
            return {"zone": zone, "loaded": 0, "total": 0, "error": f"No table for zone: {zone}"}

        card_widgets = getattr(table, "card_widgets", [])
        total = len(card_widgets)
        loaded = 0
        for panel in card_widgets:
            bmp = getattr(panel, "_card_bitmap", None)
            if bmp is not None and hasattr(bmp, "IsOk") and bmp.IsOk():
                loaded += 1
        return {"zone": zone, "loaded": loaded, "total": total}

    # ------------------------------------------------------------------ Mana symbol rendering (issue #410) ------------------------------------------------------------------

    def _handle_set_mana_search(self, text: str = "") -> dict[str, Any]:
        """Set the mana-cost search input value directly (bypasses key simulation)."""
        if not self.frame.builder_panel:
            return {"set": False, "error": "Builder panel not available"}
        if hasattr(self.frame, "_show_left_panel"):
            self.frame._show_left_panel("builder", force=True)
        ctrl = self.frame.builder_panel.inputs.get("mana")
        if ctrl is None:
            return {"set": False, "error": "Mana search input not found"}
        ctrl.ChangeValue(text)
        if hasattr(self.frame, "_on_builder_search"):
            self.frame._on_builder_search()
        return {"set": True, "text": text}

    def _handle_set_oracle_search(self, text: str = "", expand_adv: bool = True) -> dict[str, Any]:
        """Set the oracle-text search input value directly."""
        if not self.frame.builder_panel:
            return {"set": False, "error": "Builder panel not available"}
        if hasattr(self.frame, "_show_left_panel"):
            self.frame._show_left_panel("builder", force=True)
        panel = self.frame.builder_panel
        # Expand advanced filters so the oracle text input is visible
        if expand_adv:
            adv_panel = getattr(panel, "_adv_panel", None)
            if adv_panel and not adv_panel.IsShown():
                btn = getattr(panel, "_adv_toggle_btn", None)
                if btn:
                    event = wx.CommandEvent(wx.wxEVT_BUTTON, btn.GetId())
                    event.SetEventObject(btn)
                    btn.ProcessEvent(event)
        ctrl = panel.inputs.get("text")
        if ctrl is None:
            return {"set": False, "error": "Oracle text input not found"}
        ctrl.ChangeValue(text)
        if hasattr(self.frame, "_on_builder_search"):
            self.frame._on_builder_search()
        return {"set": True, "text": text}

    def _handle_screenshot_widget(
        self, widget_name: str, path: str | None = None
    ) -> dict[str, Any]:
        """Take a screenshot cropped to a specific widget's area.

        Captures the full frame via PrintWindow (so occluding windows don't
        corrupt the result) then crops to the widget's position within the frame.
        """
        import os
        import tempfile
        from datetime import datetime

        widget = self._find_mana_widget(widget_name)
        if widget is None:
            return {"error": f"Widget not found: {widget_name}"}

        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"widget_{widget_name}_{ts}.png"

        save_dir = os.path.dirname(os.path.abspath(path))
        if save_dir and not os.path.isdir(save_dir):
            path = os.path.join(tempfile.gettempdir(), os.path.basename(path))

        widget_size = widget.GetSize()
        ww, wh = widget_size.width, widget_size.height
        if ww <= 0 or wh <= 0:
            return {"error": f"Widget {widget_name!r} has zero size"}

        # Capture the full frame, then crop to the widget's client-relative rect.
        full_bmp = self._capture_window_bitmap(self.frame)
        fw, fh = full_bmp.GetWidth(), full_bmp.GetHeight()

        # Convert the widget's screen position to frame-client coordinates.
        client_pos = self.frame.ScreenToClient(widget.GetScreenPosition())
        cx = max(0, min(client_pos.x, fw - 1))
        cy = max(0, min(client_pos.y, fh - 1))
        cw = min(ww, fw - cx)
        ch = min(wh, fh - cy)

        img = full_bmp.ConvertToImage()
        cropped = img.GetSubImage(wx.Rect(cx, cy, cw, ch))

        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        log_null = wx.LogNull()
        ok = cropped.SaveFile(path, wx.BITMAP_TYPE_PNG)
        del log_null
        if not ok:
            raise RuntimeError(f"Failed to save widget screenshot to {path!r}")

        try:
            fd = os.open(path, os.O_RDONLY)
            os.fsync(fd)
            os.close(fd)
        except OSError:
            pass

        return {"path": os.path.abspath(path), "width": cw, "height": ch}

    def _find_mana_widget(self, name: str) -> wx.Window | None:
        """Resolve a named widget for screenshot purposes."""
        base = self._find_widget(name)
        if base:
            return base
        extra: dict[str, wx.Window | None] = {}
        if self.frame.builder_panel:
            mana_ctrl = self.frame.builder_panel.inputs.get("mana")
            text_ctrl = self.frame.builder_panel.inputs.get("text")
            extra["mana_search"] = mana_ctrl
            extra["oracle_search"] = text_ctrl
        inspector = getattr(self.frame, "card_inspector_panel", None)
        if inspector:
            extra["oracle_display"] = getattr(inspector, "text_ctrl", None)
        oracle_panel = getattr(self.frame, "oracle_text_ctrl", None)
        extra["oracle_panel"] = oracle_panel
        return extra.get(name)

    def _handle_add_lorem_mana_card(self) -> dict[str, Any]:
        """Insert a dummy card with LOREM_MANA oracle text into the card manager."""
        from utils.constants import LOREM_MANA

        card_manager = None
        if hasattr(self.frame, "controller") and hasattr(self.frame.controller, "card_manager"):
            card_manager = self.frame.controller.card_manager

        if card_manager is None:
            return {"added": False, "error": "Card manager not available"}

        dummy_name = "_LoremMana_Test_Card_"
        dummy_entry: dict[str, Any] = {
            "name": dummy_name,
            "mana_cost": "{W}{U}",
            "oracle_text": LOREM_MANA,
            "type_line": "Instant",
            "mana_value": 2,
            "color_identity": ["W", "U"],
        }
        # Store in the card manager's in-memory data if possible
        try:
            if hasattr(card_manager, "_data") and isinstance(card_manager._data, dict):
                card_manager._data[dummy_name.lower()] = dummy_entry
            elif hasattr(card_manager, "_cards") and isinstance(card_manager._cards, dict):
                card_manager._cards[dummy_name.lower()] = dummy_entry
            else:
                return {"added": False, "error": "Cannot access card manager data store"}
        except Exception as exc:
            return {"added": False, "error": str(exc)}

        return {"added": True, "name": dummy_name, "oracle_text": LOREM_MANA}

    def _handle_get_inspector_oracle_text(self) -> dict[str, Any]:
        """Return the plain-text value of the card inspector's oracle text control."""
        inspector = getattr(self.frame, "card_inspector_panel", None)
        if inspector is None:
            return {"text": "", "error": "Card inspector not available"}
        ctrl = getattr(inspector, "text_ctrl", None)
        if ctrl is None:
            return {"text": "", "error": "Oracle text control not found"}
        value = ctrl.GetValue() if hasattr(ctrl, "GetValue") else ""
        return {"text": value}
