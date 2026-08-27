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
        if not self._add_search_card_to_zone(zone, name):
            return
        self._focus_card_in_zone(zone, name)

    def _add_search_card_to_zone(self: AppFrame, zone: str, name: str, count: int = 1) -> bool:
        """Add ``count`` copies of a search result to ``zone``; report whether it happened.

        Every route out of the card search — the Add buttons, the 1-4 / Shift+1-4
        hotkeys, '+', and the double-click added in #1027 — funnels through here
        so the record-mode lock has exactly one place to hold. During a
        sideboard-guide record walk the search is closed for business: that walk
        diffs the current mainboard against the base 75 to derive the matchup's
        plan, so a card added from the search would be recorded as "bring this
        in" for a card that is nowhere in the 75 (see #1027). Locking the search
        for the duration is what keeps the recorded entry a sideboarding plan
        rather than a deck edit.
        """
        if self._is_recording_guide():
            self._set_status("builder.locked.recording")
            return False
        self._handle_zone_delta(zone, name, count)
        return True

    def _show_deck_tables_tab(self: AppFrame) -> bool:
        """Bring the mainboard/sideboard page of the deck workspace to the front.

        Located by identity rather than by index or by tab text: the page order
        is a construction detail and the label is translated, so both are the
        wrong thing to match on. Returns whether the page was found, so a caller
        can tell "already showing" from "no such page" (there is none before the
        centre panel is built).
        """
        notebook = getattr(self, "deck_tabs", None)
        page = getattr(self, "deck_split", None)
        if notebook is None or page is None:
            return False
        for index in range(notebook.GetPageCount()):
            if notebook.GetPage(index) is page:
                if notebook.GetSelection() != index:
                    notebook.SetSelection(index)
                return True
        return False

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
