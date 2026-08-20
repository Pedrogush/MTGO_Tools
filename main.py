#!/usr/bin/env python3
"""wxPython entry point that launches the deck builder directly."""

from __future__ import annotations

import argparse
import os
import sys

import wx
from loguru import logger

from utils.constants import BASE_DATA_DIR, LOGS_DIR, ensure_base_dirs
from utils.logging_config import configure_logging
from utils.runtime_flags import set_automation_enabled
from widgets.frames.app_frame import make_app_frame
from widgets.frames.splash_frame import LoadingFrame
from widgets.native_dark import enable_app_dark_mode
from widgets.panels.card_table_panel.marquee import is_background_window

# Global flag for automation mode
_automation_enabled = False
_automation_port = 19847


class MetagameWxApp(wx.App):
    """Bootstrap the redesigned deck builder."""

    def FilterEvent(self, event: wx.Event) -> int:  # noqa: N802 - wx override
        """Start a marquee when a left-press lands on a background surface.

        Runs before any window sees the event, so a press on a non-interactive
        zone — which binds no handler of its own — can still begin the active
        deck view's rubber-band selection, letting the box be drawn from
        anywhere in the window. The press is classified at down time: a plain
        background surface (see :func:`is_background_window`) starts a marquee;
        anything else — a real control, or a card/row inside a card view — is
        left untouched so its own click or drag-to-reorder gesture wins. The
        card views begin their own marquee from an empty-space press, so those
        are intentionally not background here.

        Always returns -1 (continue normal processing): the filter only *adds*
        the marquee start on top of the press, it never consumes it.
        """
        if event.GetEventType() == wx.wxEVT_LEFT_DOWN and is_background_window(
            event.GetEventObject()
        ):
            top = self.GetTopWindow()
            begin = getattr(top, "begin_active_marquee", None)
            if callable(begin):
                begin(wx.GetMousePosition(), additive=event.ShiftDown())
        return -1

    def OnInit(self) -> bool:  # noqa: N802 - wx override
        logger.info("Starting MTGO Tools (wx)")
        # Before the first window: controls read the process's preferred app mode
        # when their HWND is created, so this must precede LoadingFrame. It is
        # what makes wx.Choice, checkbox glyphs, list headers and every scrollbar
        # dark — none of which wx can colour itself. No-op off Windows.
        enable_app_dark_mode()
        if _automation_enabled:
            logger.info(f"Automation server will start on port {_automation_port}")
        self.loading_frame = LoadingFrame()
        self.loading_frame.Show()
        self.loading_frame.Layout()
        self.loading_frame.Refresh()
        self.loading_frame.Update()
        wx.CallAfter(self._build_main_window)
        return True

    def _build_main_window(self) -> None:
        frame = make_app_frame()
        controller = frame.controller
        self.controller = controller
        self.SetTopWindow(frame)

        # Start automation server if enabled
        self._automation_server = None
        if _automation_enabled:
            try:
                from automation.server import AutomationServer

                self._automation_server = AutomationServer(controller.frame, port=_automation_port)
                self._automation_server.start()
                logger.info(f"Automation server started on port {_automation_port}")
            except Exception as e:
                logger.error(f"Failed to start automation server: {e}")

        def show_main() -> None:
            frame = controller.frame
            frame.Freeze()
            frame.Layout()
            frame.SendSizeEvent()
            frame.Thaw()
            frame.Show()
            frame.Refresh()
            frame.Update()
            wx.CallAfter(frame.ensure_card_data_loaded)

        if getattr(self, "loading_frame", None):
            self.loading_frame.set_ready(show_main)
        else:
            show_main()

    def OnExit(self) -> int:  # noqa: N802 - wx override
        if getattr(self, "_automation_server", None):
            logger.info("Stopping automation server...")
            self._automation_server.stop()
        return 0

    def OnExceptionInMainLoop(self) -> bool:  # noqa: N802 - wx override
        import sys
        import traceback

        exc_type, exc_value, exc_traceback = sys.exc_info()
        logger.error("=== UNHANDLED EXCEPTION IN MAIN LOOP ===")
        logger.error(f"Exception type: {exc_type.__name__}")
        logger.error(f"Exception value: {exc_value}")
        logger.error("Traceback:")
        for line in traceback.format_tb(exc_traceback):
            logger.error(line.rstrip())
        logger.error("=== END UNHANDLED EXCEPTION ===")

        # Show error dialog to user
        error_msg = f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc_value}\n\nCheck the log file for details."
        wx.MessageBox(error_msg, "Application Error", wx.OK | wx.ICON_ERROR)

        # Return True to continue running, False to exit
        return True


def _ensure_mana_assets() -> None:
    """Fetch the mana symbol assets on first run if they are missing.

    Runs once, before the UI is built, so mana icons render without a manual
    ``scripts/fetch_mana_assets.py`` step. On every subsequent launch the assets
    are already present and this is a cheap local check. Any failure (no network,
    git unavailable, running frozen) is non-fatal: the mana icon factory falls
    back to placeholder glyphs, so we log and continue.
    """
    try:
        from scripts.fetch_mana_assets import ensure_mana_assets, mana_assets_present

        if mana_assets_present():
            return
        logger.info("Mana assets missing; fetching on first run…")
        if ensure_mana_assets(quiet=True):
            logger.info("Mana assets fetched successfully.")
        else:
            logger.warning(
                "Could not fetch mana assets; mana symbols will use fallback glyphs. "
                "Run scripts/fetch_mana_assets.py to retry."
            )
    except Exception as exc:  # pragma: no cover - defensive; never block startup
        logger.warning(f"Skipping mana asset fetch: {exc}")


def _set_windows_app_id() -> None:
    """Give the app an explicit Windows AppUserModelID.

    Without this, Windows associates the taskbar button with the Python /
    PyInstaller host process and shows *its* icon; setting an explicit ID makes
    the taskbar use the app's own window icon and groups it as its own app.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MTGOTools.DeckBuilder")
    except Exception as exc:  # pragma: no cover - windows-only, best effort
        logger.debug(f"Could not set AppUserModelID: {exc}")


def debugpy_server() -> None:
    # Runs optionally: only starts when the MTGO_TOOLS_INSTALL_DEBUG env var is set.
    """Start a debugpy server so a packaged build can be debugged.

    Installed builds are windowed (no console) and have no debugger attached, so
    to step through one the same way you would from the IDE you attach a remote
    debugger. This is enabled only when ``MTGO_TOOLS_INSTALL_DEBUG`` is set, so
    it is inert in normal use and in shipped builds:

    * ``MTGO_TOOLS_INSTALL_DEBUG=1`` listens on the default port (5678).
    * ``MTGO_TOOLS_INSTALL_DEBUG=<port>`` listens on that port instead.
    * ``MTGO_TOOLS_INSTALL_DEBUG_WAIT=1`` blocks startup until the IDE attaches,
      so you can break on early startup code.

    Then use your IDE's "attach to a running process / port" to connect. Any
    failure (debugpy not bundled, port in use) is logged and non-fatal.
    """
    flag = os.environ.get("MTGO_TOOLS_INSTALL_DEBUG")
    if not flag:
        return
    port = int(flag) if flag.isdigit() else 5678
    try:
        import debugpy

        debugpy.listen(("127.0.0.1", port))
        logger.info(f"debugpy listening on 127.0.0.1:{port} — attach your IDE to this process")
        if os.environ.get("MTGO_TOOLS_INSTALL_DEBUG_WAIT"):
            logger.info("MTGO_TOOLS_INSTALL_DEBUG_WAIT set; waiting for a debugger to attach…")
            debugpy.wait_for_client()
            logger.info("Debugger attached.")
    except Exception as exc:  # pragma: no cover - dev-only tooling
        logger.warning(f"Could not start debugpy ({exc}); continuing without a debugger.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MTGO Tools")
    parser.add_argument(
        "--automation",
        action="store_true",
        help=(
            "Enable automation server for CLI control. Dev/test-only: binds to "
            "127.0.0.1 with no auth. Disabled by default; never enabled in "
            "packaged builds. See automation/README.md for the security boundary."
        ),
    )
    parser.add_argument(
        "--automation-port",
        type=int,
        default=19847,
        help="Port for automation server (default: 19847)",
    )
    return parser.parse_args()


def main() -> None:
    global _automation_enabled, _automation_port

    args = parse_args()
    _automation_enabled = args.automation
    _automation_port = args.automation_port
    set_automation_enabled(_automation_enabled)

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")
    logger.info(f"Using base data directory: {BASE_DATA_DIR}")

    _set_windows_app_id()
    debugpy_server()

    _ensure_mana_assets()

    if _automation_enabled:
        logger.info(f"Automation mode enabled on port {_automation_port}")

    # Install global exception handler for exceptions outside of wx mainloop
    import traceback

    def global_exception_handler(exc_type, exc_value, exc_traceback):
        logger.error("=== UNCAUGHT EXCEPTION (GLOBAL) ===")
        logger.error(f"Exception type: {exc_type.__name__}")
        logger.error(f"Exception value: {exc_value}")
        logger.error("Traceback:")
        for line in traceback.format_tb(exc_traceback):
            logger.error(line.rstrip())
        logger.error("=== END UNCAUGHT EXCEPTION ===")

        # Call default handler
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = global_exception_handler

    app = MetagameWxApp(False)
    app.MainLoop()


if __name__ == "__main__":
    import multiprocessing

    # Frozen (PyInstaller) builds use multiprocessing "spawn", which re-launches
    # this executable for each child process. freeze_support() makes those
    # children run their worker target instead of re-starting the whole app
    # (without it, image-service workers exit without returning a result).
    multiprocessing.freeze_support()
    main()
