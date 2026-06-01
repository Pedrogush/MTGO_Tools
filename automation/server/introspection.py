"""Introspection / generic interaction command handlers.

Covers ping, status/window info, widget listing & clicking, waiting, opening
top-level widgets, closing the app, and reading the inspector oracle text.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import wx

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class IntrospectionMixin(_Base):
    """Generic app introspection and interaction commands."""

    def _handle_ping(self) -> dict[str, Any]:
        """Handle ping command."""
        return {"status": "ok", "timestamp": time.time()}

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

    def _handle_wait(self, ms: int = 1000) -> dict[str, Any]:
        """Wait for a specified number of milliseconds."""
        time.sleep(ms / 1000.0)
        return {"waited": ms}

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
