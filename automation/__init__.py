"""
Automation module for CLI control of the MTGO Tools application.

This module provides:
- AutomationServer: Socket server that runs inside the wxPython app
- AutomationClient: Client library for sending commands
- CLI: Command-line interface for manual testing and scripting
"""

from automation.server import AutomationServer
from automation.client import AutomationClient

__all__ = ["AutomationServer", "AutomationClient"]
