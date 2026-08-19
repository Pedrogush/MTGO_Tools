"""The main window's menu bar (phase 3b of the UI redesign, issue #962)."""

from widgets.menu_bar.panel import AppMenuBar, build_menu
from widgets.menu_bar.spec import MenuEntry, MenuSpec, describe, invoke_entry, separator

__all__ = [
    "AppMenuBar",
    "MenuEntry",
    "MenuSpec",
    "build_menu",
    "describe",
    "invoke_entry",
    "separator",
]
