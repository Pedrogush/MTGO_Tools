"""Deck-builder command handlers: search, advanced filters, results scrolling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class BuilderMixin(_Base):
    """Deck-builder panel command handlers."""

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
