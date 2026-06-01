"""Socket transport, lifecycle, and the command-handler registry/dispatch."""

from __future__ import annotations

import json
import socket
import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

BUFFER_SIZE = 65536

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class TransportMixin(_Base):
    """Socket server loop, client handling, and command dispatch."""

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
