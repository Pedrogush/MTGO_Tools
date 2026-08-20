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
        """Get window information.

        ``min_size`` is the frame's enforced floor -- the number the redesign's
        "does this still fit a 1366x768 laptop" criterion is measured against.
        It is recomputed by ``AppFrame._apply_min_size`` whenever a side panel is
        collapsed or expanded, so toggling one (``click left_toggle`` twice) is
        how to refresh it after the window's content has changed.
        ``content_min_size`` is what the root panel's sizer wants *right now*,
        which is the same number before the frame chrome is added -- when the two
        disagree, the enforced floor is stale.
        """
        pos = self.frame.GetPosition()
        size = self.frame.GetSize()
        min_size = self.frame.GetMinSize()
        info: dict[str, Any] = {
            "title": self.frame.GetTitle(),
            "position": {"x": pos.x, "y": pos.y},
            "size": {"width": size.width, "height": size.height},
            "min_size": {"width": min_size.width, "height": min_size.height},
            "visible": self.frame.IsShown(),
            "active": self.frame.IsActive(),
            "left_collapsed": getattr(self.frame, "_left_collapsed", None),
            "inspector_collapsed": getattr(self.frame, "_inspector_collapsed", None),
        }
        root_panel = getattr(self.frame, "root_panel", None)
        root_sizer = root_panel.GetSizer() if root_panel else None
        if root_sizer is not None:
            content_min = root_sizer.GetMinSize()
            info["content_min_size"] = {
                "width": content_min.GetWidth(),
                "height": content_min.GetHeight(),
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

        # Menu bar (six toolbar buttons + a gear popup until phase 3b)
        menu_bar = getattr(self.frame, "menu_bar", None)
        if menu_bar is not None:
            widgets["menu_bar"] = {
                "type": "AppMenuBar",
                "titles": menu_bar.titles(),
                "buttons": self._get_button_info(menu_bar),
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

    @staticmethod
    def _walk_buttons(parent: wx.Window) -> list[wx.Button]:
        """Every ``wx.Button`` under ``parent``, nearest first (review §5.7).

        Breadth-first, deliberately: this used to look at ``GetChildren()`` one
        level deep, so any button the panel wrapped in a sub-panel was
        unreachable by label — and phase 7 wraps two of them (the mode switch,
        :mod:`widgets.mode_switch`). Searching nearest-first keeps a direct child
        winning over a deeper namesake, which is what the old behaviour promised
        for the cases it did handle.
        """
        found: list[wx.Button] = []
        frontier = [parent]
        while frontier:
            nxt: list[wx.Window] = []
            for window in frontier:
                for child in window.GetChildren():
                    if isinstance(child, wx.Button):
                        found.append(child)
                    nxt.append(child)
            frontier = nxt
        return found

    def _get_button_info(self, parent: wx.Window) -> list[dict[str, Any]]:
        """Get info about buttons in a widget."""
        return [
            {
                "label": button.GetLabel(),
                "enabled": button.IsEnabled(),
                "id": button.GetId(),
            }
            for button in self._walk_buttons(parent)
        ]

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

        # Search for button by label within the widget, at any depth (§5.7).
        if label:
            for child in self._walk_buttons(target):
                if child.GetLabel() == label:
                    event = wx.CommandEvent(wx.wxEVT_BUTTON, child.GetId())
                    event.SetEventObject(child)
                    child.ProcessEvent(event)
                    return {"clicked": True, "widget": widget, "label": label}

        return {"clicked": False, "error": f"Button not found: {label}"}

    def _find_widget(self, name: str) -> wx.Window | None:
        """Find a widget by name."""
        widget_map = {
            "menu_bar": getattr(self.frame, "menu_bar", None),
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
            "left_toggle": getattr(self.frame, "left_toggle_btn", None),
            "inspector_toggle": getattr(self.frame, "inspector_toggle_btn", None),
        }
        if name in widget_map:
            return widget_map[name]
        # The six companion windows, by the same names ``open_widget`` and
        # ``screenshot_window`` already use. Phase 7 made the label search walk
        # to any depth (§5.7) and phase 9 found the other half of that gap: the
        # search had no way to start at a window that is not the main frame, so
        # ``click radar --label "Generate Radar"`` answered "Widget not found:
        # radar" and every companion window's buttons were unreachable by label.
        return self._resolve_secondary_window(name)

    def _handle_focus_text_input(self, window: str | None = None, index: int = 0) -> dict[str, Any]:
        """Focus the ``index``-th text input of a top-level window.

        Added in phase 6c for the same reason phase 4 added ``select_card``: the
        state could not be reached from the harness at all. A text field's
        border now changes on focus (``BORDER_STRONG`` -> ``FOCUS_RING``, 1 DIP
        -> 2 DIP), and "does it look different focused" is a question only a
        capture of the running app answers -- the phase this replaces recorded a
        border from an isolated probe that the real app did not have.

        Returns every input it found, in traversal order, so a caller can pick
        one by description rather than by guessing an index.
        """
        target = self.frame
        if window is not None:
            resolved = self._resolve_secondary_window(window)
            if resolved is None:
                return {"focused": False, "error": f"Window {window!r} not found or not open"}
            target = resolved

        inputs: list[wx.TextCtrl] = []

        def walk(win: wx.Window) -> None:
            for child in win.GetChildren():
                if isinstance(child, wx.TextCtrl):
                    inputs.append(child)
                walk(child)

        walk(target)
        described = [
            {
                "index": i,
                "value": c.GetValue()[:40],
                "editable": c.IsEditable(),
                "enabled": c.IsEnabled(),
                "parent": type(c.GetParent()).__name__,
            }
            for i, c in enumerate(inputs)
        ]
        if not inputs:
            return {"focused": False, "error": "no text inputs in this window", "inputs": []}
        if not 0 <= index < len(inputs):
            return {
                "focused": False,
                "error": f"index {index} of {len(inputs)}",
                "inputs": described,
            }
        target.Raise()
        inputs[index].SetFocus()
        return {"focused": True, "index": index, "inputs": described}

    def _handle_wait(self, ms: int = 1000) -> dict[str, Any]:
        """Wait for a specified number of milliseconds."""
        time.sleep(ms / 1000.0)
        return {"waited": ms}

    def _handle_open_widget(self, widget_name: str) -> dict[str, Any]:
        """Open one of the six companion windows by name.

        All six are listed here as of phase 3b. Until then only four were, and
        the other two (``top_cards``, ``radar``) were reachable only through
        ``click toolbar --label ...`` -- which stopped existing when the toolbar
        became a menu bar. Review finding §5.2.
        """
        handler_map = {
            "opponent_tracker": "open_opponent_tracker",
            "match_history": "open_match_history",
            "timer_alert": "open_timer_alert",
            "metagame": "open_metagame_analysis",
            "top_cards": "open_top_cards",
            "radar": "open_radar",
        }
        method_name = handler_map.get(widget_name)
        if not method_name:
            return {"opened": False, "error": f"Unknown widget: {widget_name}"}
        method = getattr(self.frame, method_name, None)
        if method is None:
            return {"opened": False, "error": f"Method not found: {method_name}"}
        method()
        return {"opened": True, "widget": widget_name}

    def _handle_menu(self, path: str | list[str] | None = None) -> dict[str, Any]:
        """List the menu bar, or activate one item by path.

        ``path`` is ``"Tools/Radar"`` (or the equivalent list). A radio option
        takes three segments, ``"Settings/Language/pt-BR"`` -- the last segment
        matches either the option's value or its translated label.

        This drives the entry's handler directly instead of popping the menu up,
        because ``wx.PopupMenu`` runs a nested modal loop on the main thread and
        would stop this very socket being serviced (review finding §5.5).
        """
        from widgets.menu_bar import describe, invoke_entry

        menu_bar = getattr(self.frame, "menu_bar", None)
        if menu_bar is None:
            return {"ok": False, "error": "Menu bar not available"}
        if path is None:
            return {
                "ok": True,
                "menus": {title: describe(menu_bar.entries(title)) for title in menu_bar.titles()},
            }
        parts = path.split("/") if isinstance(path, str) else list(path)
        if not parts:
            return {"ok": False, "error": "Empty menu path"}
        title, rest = parts[0], parts[1:]
        if title not in menu_bar.titles():
            return {"ok": False, "error": f"Menu not found: {title}"}
        if not rest:
            return {"ok": False, "error": f"No item given under {title!r}"}
        if invoke_entry(menu_bar.entries(title), rest):
            return {"ok": True, "path": parts}
        return {"ok": False, "error": f"Menu item not found: {'/'.join(parts)}"}

    def _handle_preferences(
        self, key: str | None = None, value: str | None = None
    ) -> dict[str, Any]:
        """List the preferences, or set one by key.

        Phase 7 collapsed the ``Settings`` menu into a modal dialog, and
        ``wx.Dialog.ShowModal`` starves this socket exactly the way
        ``wx.PopupMenu`` does (§5.5) -- so the harness drives the *spec* the
        dialog renders, never the dialog. ``key`` is the stable name
        (``deck_data_source``, ``language``, ``average_method``,
        ``average_hours``, ``check_for_updates``); ``value`` is the option's
        value or its translated label, or ``on``/``off``/``toggle`` for a
        boolean.
        """
        from widgets.preferences import apply_preference, describe

        build = getattr(self.frame, "preference_groups", None)
        if build is None:
            return {"ok": False, "error": "Preferences not available"}
        groups = build()
        if key is None:
            return {"ok": True, "groups": describe(groups)}
        if value is None:
            return {"ok": False, "error": f"No value given for preference {key!r}"}
        if apply_preference(groups, key, value):
            return {"ok": True, "key": key, "value": value}
        return {"ok": False, "error": f"Preference not set: {key}={value}"}

    def _handle_refresh_collection(self, force: bool = True) -> dict[str, Any]:
        """Trigger a collection refresh + export through the real controller path.

        Drives ``AppController.refresh_collection_from_bridge`` (the same code the
        "Load Collection" toolbar menu item runs), which fetches a snapshot from the
        MTGO bridge on a background thread and writes a ``collection_full_trade_*.json``
        export into the deck save directory. Returns immediately; poll ``save_dir`` for
        the new file and ``get_status`` for the success/failure message.
        """
        controller = getattr(self.frame, "controller", None)
        if controller is None:
            return {"triggered": False, "error": "Controller not available"}
        save_dir = getattr(controller, "deck_save_dir", None)
        controller.refresh_collection_from_bridge(force=force)
        return {"triggered": True, "save_dir": str(save_dir) if save_dir else None}

    def _handle_timer_alert_action(self, action: str) -> dict[str, Any]:
        """Drive the open Timer Alert window (start/stop monitoring, test alert)."""
        win = getattr(self.frame, "timer_window", None)
        if win is None:
            return {"ok": False, "error": "Timer alert window is not open"}
        method_name = {
            "start": "start_monitoring",
            "stop": "stop_monitoring",
            "test": "test_alert",
        }.get(action)
        if method_name is None:
            return {"ok": False, "error": f"Unknown action: {action}"}
        method = getattr(win, method_name, None)
        if method is None:
            return {"ok": False, "error": f"Method not found: {method_name}"}
        method()
        status = win.status_text.GetValue() if hasattr(win, "status_text") else None
        return {"ok": True, "action": action, "status": status}

    def _handle_close_app(self) -> dict[str, Any]:
        """Close the application after sending the response."""
        # Schedule Close on the next event-loop iteration so the response is
        # sent back to the client before the wx app exits.
        wx.CallAfter(self.frame.Close, True)
        return {"closed": True}

    def _handle_select_card(self, card_name: str, zone: str = "main") -> dict[str, Any]:
        """Select a card by name in a deck zone, populating the Card Inspector.

        Added in phase 4: the inspector's card-selected state (the printing
        pager, "Save art", the wrapped-title + mana-pip row) was unreachable
        from the harness, so F6 and A6 could not be verified on screen without
        a real mouse click. ``focus_card`` is the panel's own selection entry
        point, so this drives exactly the path a click drives.
        """
        panel = getattr(self.frame, "main_table" if zone == "main" else "side_table", None)
        if panel is None:
            return {"selected": False, "error": f"Zone not available: {zone}"}
        focus = getattr(panel, "focus_card", None)
        if not callable(focus):
            return {"selected": False, "error": "Panel has no focus_card"}
        ok = bool(focus(card_name))
        return {"selected": ok, "card_name": card_name, "zone": zone}

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
