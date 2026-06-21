"""Card-content population and dependency wiring for the card inspector panel.

The public ``reset``/``update_card`` populators that fill the header, type,
stats, oracle, and mana-cost widgets, plus the dependency setters
(``set_card_manager``/``set_bulk_data``/``set_*_handler``) that wire the panel
into its collaborators.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

from utils.constants import SUBDUED_TEXT, ZONE_TITLES

if TYPE_CHECKING:
    from repositories.card_repository import CardDataManager
    from services.image_service import CardImageRequest
    from widgets.panels.card_inspector_panel.protocol import CardInspectorPanelProto

    _Base = CardInspectorPanelProto
else:
    _Base = object


class ContentMixin(_Base):
    """Public ``reset``/``update_card`` populators and dependency setters."""

    # ============= Public API =============

    def reset(self) -> None:
        self.active_zone = None
        self.name_label.SetLabel("Select a card to inspect.")
        self.type_label.SetLabel("")
        self.stats_label.SetLabel("")
        self.text_ctrl.ChangeValue("Select a card to inspect.")
        self.image_text_ctrl.ChangeValue("Select a card to inspect.")
        self._render_mana_cost("")
        self.card_image_display.show_placeholder("Select a card")
        self.nav_panel.Hide()
        self.save_panel.Hide()
        self.inspector_printings = []
        self.inspector_current_printing = 0
        self.inspector_selection = None
        self.inspector_current_card_name = None
        self._printings_request_inflight = None
        self._loading_printing = False
        self._has_selection = False
        self._image_request_name = None
        self._emit_printing_changed()
        self._set_display_mode(False, show_image_column=True)

    def update_card(
        self,
        card: dict[str, Any],
        zone: str | None = None,
        meta: dict[str, Any] | None = None,
        selection: dict[str, Any] | None = None,
    ) -> None:
        self.active_zone = zone
        self._has_selection = True
        # The printing this card should open on (its saved board art), applied
        # once the printing list is known (issue #792, part 1b).
        self.inspector_selection = selection
        zone_title = ZONE_TITLES.get(zone, zone.title()) if zone else "Card Search"
        header = f"{card['name']}  ×{card['qty']}  ({zone_title})"
        self.name_label.SetLabel(header)

        # Get or use metadata. Skip the manager fallback unless it has finished
        # loading — calling get_card on an unloaded CardDataManager raises.
        if meta is None and self.card_manager and self.card_manager.is_loaded:
            meta = self.card_manager.get_card(card["name"]) or {}
        else:
            meta = meta or {}
        self._image_request_name = self._resolve_image_request_name(card, meta)

        # Render mana cost
        mana_cost = meta.get("mana_cost", "")
        self._render_mana_cost(mana_cost)

        # Type line
        type_line = meta.get("type_line") or "Type data unavailable."
        self.type_label.SetLabel(type_line)

        # Stats line
        stats_bits: list[str] = []
        if meta.get("mana_value") is not None:
            stats_bits.append(f"MV {meta['mana_value']}")
        if meta.get("power") or meta.get("toughness"):
            stats_bits.append(f"P/T {meta.get('power', '?')}/{meta.get('toughness', '?')}")
        if meta.get("loyalty"):
            stats_bits.append(f"Loyalty {meta['loyalty']}")
        colors = meta.get("color_identity", [])
        stats_bits.append(f"Colors: {'/'.join(colors) if colors else 'Colorless'}")
        stats_bits.append(f"Zone: {zone_title}")
        self.stats_label.SetLabel("  |  ".join(stats_bits))

        # Oracle text
        oracle_text = meta.get("oracle_text") or ""
        self.text_ctrl.ChangeValue(oracle_text)
        self.image_text_ctrl.ChangeValue(oracle_text or "Text unavailable.")

        # Load image and printings
        self._load_card_image_and_printings(card["name"])

    def set_card_manager(self, card_manager: CardDataManager) -> None:
        self.card_manager = card_manager

    def set_bulk_data(self, bulk_data_by_name: dict[str, list[dict[str, Any]]]) -> None:
        self.bulk_data_by_name = bulk_data_by_name
        if self.inspector_current_card_name:
            self._load_card_image_and_printings(self.inspector_current_card_name)

    def set_image_request_handlers(
        self,
        *,
        on_request: Callable[[CardImageRequest], None] | None,
        on_selected: Callable[[CardImageRequest | None], None] | None,
    ) -> None:
        self._image_request_handler = on_request
        self._selected_card_handler = on_selected

    def set_printings_request_handler(self, handler: Callable[[str], None] | None) -> None:
        self._printings_request_handler = handler

    def set_printing_changed_handler(
        self, handler: Callable[[dict[str, Any] | None], None] | None
    ) -> None:
        """Register a callback fired whenever the displayed printing changes."""
        self._printing_changed_handler = handler

    def set_printing_selected_handler(
        self, handler: Callable[[dict[str, Any], bool], None] | None
    ) -> None:
        """Register a callback fired on user-driven printing changes (#792).

        ``handler(printing, persist)`` runs on prev/next clicks (``persist`` =
        the auto-save flag) and on the explicit Save-art button (``persist`` =
        True). It drives the board-art sync and the save-the-choice behaviour;
        async loads and resets do not fire it.
        """
        self._printing_selected_handler = handler

    # ============= Private Methods =============

    def _render_mana_cost(self, mana_cost: str) -> None:
        self.cost_sizer.Clear(delete_windows=True)
        if mana_cost:
            panel = self.mana_icons.render(self.cost_container, mana_cost)
            panel.SetMinSize((max(32, panel.GetBestSize().width), 32))
        else:
            panel = wx.StaticText(self.cost_container, label="—")
            panel.SetForegroundColour(SUBDUED_TEXT)
        self.cost_sizer.Add(panel, 0)
        self.cost_container.Layout()
