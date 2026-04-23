#!/usr/bin/env python3
"""wxPython entry point that launches the deck builder directly."""

from __future__ import annotations

import argparse

import wx
from loguru import logger

from controllers.app_controller import get_deck_selector_controller
from utils.constants import BASE_DATA_DIR, LOGS_DIR, ensure_base_dirs
from utils.logging_config import configure_logging
from utils.runtime_flags import set_automation_enabled
from widgets.frames.splash_frame import LoadingFrame

# Global flag for automation mode
_automation_enabled = False
_automation_port = 19847


class MetagameWxApp(wx.App):
    """Bootstrap the redesigned deck builder."""

    def OnInit(self) -> bool:  # noqa: N802 - wx override
        logger.info("Starting MTGO Metagame Deck Builder (wx)")
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
        controller = get_deck_selector_controller()
        self.controller = controller
        self.SetTopWindow(controller.frame)

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="MTGO Metagame Deck Builder")
    parser.add_argument(
        "--automation",
        action="store_true",
        help="Enable automation server for CLI control",
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

    if _automation_enabled:
        logger.info(f"Automation mode enabled on port {_automation_port}")

    # Install global exception handler for exceptions outside of wx mainloop
    import sys
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
    main()
