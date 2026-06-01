"""Mana-symbol rendering command handlers (issue #410).

Covers setting the mana/oracle search inputs, resolving named mana-related
widgets for screenshots, and injecting a LOREM_MANA test card.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class ManaRenderingMixin(_Base):
    """Mana / oracle search inputs and mana-widget resolution."""

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
        card_panel = getattr(self.frame, "card_panel", None)
        if card_panel is not None:
            extra["card_panel"] = card_panel
            extra["oracle_panel"] = getattr(card_panel, "oracle_html", None)
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
