"""Selection / focus / table-routing handlers for deck zones."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto
    from widgets.panels.card_table_panel import CardTablePanel

    _Base = AppFrameProto
else:
    _Base = object


class CardSelectionHandlers(_Base):
    """Resolve the selected/active card and route focus across zone tables."""

    def _get_selected_zone_card(self: AppFrame) -> tuple[str, dict[str, Any]] | None:
        for zone, table in (
            ("main", self.main_table),
            ("side", self.side_table),
            ("out", self.out_table),
        ):
            if not table:
                continue
            selected = table.get_selected_card()
            if selected:
                return zone, selected
        return None

    def _get_selected_search_card(self: AppFrame) -> dict[str, Any] | None:
        if not self.builder_panel:
            return None
        return self.builder_panel.get_selected_result()

    def _has_selected_card(self: AppFrame) -> bool:
        return (
            self._get_selected_zone_card() is not None
            or self._get_selected_search_card() is not None
        )

    def _clear_zone_selections(self: AppFrame) -> None:
        for table in (self.main_table, self.side_table, self.out_table):
            if table:
                table.clear_selection()

    def _get_active_zone_for_add(self: AppFrame) -> str:
        # Mainboard and sideboard are visible at once (#781), so there is no
        # active tab to disambiguate; use the zone the user last interacted with.
        zone = getattr(self, "_active_deck_zone", "main")
        return zone if zone in {"main", "side"} else "main"

    def _add_search_card_to_active_zone(self: AppFrame, name: str) -> None:
        zone = self._get_active_zone_for_add()
        self._handle_zone_delta(zone, name, 1)
        self._focus_card_in_zone(zone, name)

    def _focus_card_in_zone(self: AppFrame, zone: str, card_name: str) -> None:
        table = self._get_table_for_zone(zone)
        if not table:
            return
        self._collapse_other_zone_tables(zone)
        table.focus_card(card_name)

    def _get_table_for_zone(self: AppFrame, zone: str) -> CardTablePanel | None:
        if zone == "main":
            return self.main_table
        if zone == "side":
            return self.side_table
        if zone == "out":
            return self.out_table
        return None

    def _collapse_other_zone_tables(self, active_zone: str) -> None:
        tables = {
            "main": self.main_table,
            "side": self.side_table,
            "out": self.out_table,
        }
        for zone, table in tables.items():
            if zone == active_zone:
                continue
            if table:
                table.collapse_active()
