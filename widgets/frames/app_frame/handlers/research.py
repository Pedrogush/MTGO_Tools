"""Deck-research handlers: format/archetype selection, deck filters, and loads."""

from __future__ import annotations

import time
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from widgets.frames.app_frame.handlers.deck_formatting import (
    normalize_date,
    simple_summary_html,
    strip_extra_dates,
)
from widgets.panels.deck_research_panel.results_filter import filter_decks

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class DeckResearchHandlers(_Base):
    """Format/archetype selection, deck-filter callbacks, and deck loading."""

    # UI Event Handlers
    def on_format_changed(self: AppFrame) -> None:
        self.current_format = self.research_panel.get_selected_format()
        self.card_panel.update_format(self.current_format)
        self.card_panel.update_archetype(None)
        # Use stale-while-revalidate (same as startup): serve cached/stale
        # archetypes for the new format immediately and refresh in the
        # background. force=True is reserved for the explicit reload action.
        self.fetch_archetypes()

    def on_archetype_filter(self: AppFrame) -> None:
        query = self.research_panel.get_search_query()
        if not query:
            self.filtered_archetypes = list(self.archetypes)
        else:
            self.filtered_archetypes = [
                entry for entry in self.archetypes if query in entry.get("name", "").lower()
            ]
        self._populate_archetype_list()

    def on_archetype_selected(self: AppFrame) -> None:
        with self._loading_lock:
            if self.loading_archetypes or self.loading_decks:
                return
        idx = self.research_panel.get_selected_archetype_index()
        if idx < 0:
            return
        if idx == 0:  # "Any" — load all cached decks sorted by date
            self.card_panel.update_archetype(None)
            self._load_decks(scope="all")
            return
        archetype = self.filtered_archetypes[idx - 1]
        self.card_panel.update_archetype(archetype, radar_data=None)
        self._load_decks(scope="archetype", archetype=archetype)
        self._load_radar_in_background(archetype)

    def on_event_type_filter_changed(self: AppFrame) -> None:
        self._apply_deck_filters()

    def on_placement_filter_changed(self: AppFrame) -> None:
        self._apply_deck_filters()

    def on_player_name_filter_changed(self: AppFrame) -> None:
        self._schedule_filter_debounce()

    def on_date_filter_changed(self: AppFrame) -> None:
        self._schedule_filter_debounce()

    def _apply_deck_filters(self: AppFrame) -> None:
        event_type = self.research_panel.get_event_type_filter()
        placement_op, placement_field, placement_value = self.research_panel.get_placement_filter()
        player_query = self.research_panel.get_player_name_filter()
        date_query = self.research_panel.get_date_filter()

        self.controller.session_manager.update_deck_event_type_filter(event_type)
        self.controller.session_manager.update_deck_placement_filter(
            placement_op, placement_field, placement_value
        )
        self.controller.session_manager.update_deck_player_filter(player_query)
        self.controller.session_manager.update_deck_date_filter(date_query)
        self._schedule_settings_save()

        filtered = filter_decks(
            list(self._all_loaded_decks),
            event_type,
            placement_op=placement_op,
            placement_field=placement_field,
            placement_value=placement_value,
            player_query=player_query,
            date_query=date_query,
        )
        self.controller.deck_repo.set_decks_list(filtered)
        self.deck_list.Clear()
        if not filtered:
            self.deck_list.Append(self._t("deck_results.no_decks"))
            self.deck_list.Disable()
            return
        slug_to_name = {a.get("href", ""): a.get("name", "") for a in self.archetypes}
        show_source = self.controller.get_deck_data_source() == "both"
        rows = [
            (
                (
                    ("🐠" if deck.get("source") == "mtggoldfish" else "🧙🏾‍♂️")
                    if show_source
                    else ""
                ),
                deck.get("player", "Unknown"),
                slug_to_name.get(deck.get("name", ""), deck.get("name", "")),
                strip_extra_dates(deck.get("event", "")),
                deck.get("result", ""),
                normalize_date(deck.get("date", "")),
            )
            for deck in filtered
        ]
        self.deck_list.set_decks(rows)
        self.deck_list.Enable()

    # Async Callback Handlers
    def _on_archetypes_loaded(self: AppFrame, items: list[dict[str, Any]]) -> None:
        with self._loading_lock:
            self.loading_archetypes = False
        self.archetypes = sorted(items, key=lambda entry: entry.get("name", "").lower())
        self.filtered_archetypes = list(self.archetypes)
        self._populate_archetype_list()
        self.research_panel.enable_controls()
        count = len(self.archetypes)
        self._set_status("app.research.archetypes_loaded", count=count, format=self.current_format)
        # populate_archetypes resets the combo selection to "Any" (index 0) via
        # SetSelection, which does not fire EVT_COMBOBOX. Load decks explicitly
        # so the list reflects the newly loaded format on startup and on every
        # format change — otherwise it shows stale results from the previous
        # format.
        #
        # Archetype fetch uses stale-while-revalidate, so this callback fires
        # twice per fetch: once with the cached/stale list and again with the
        # background-refreshed list. The "Any" deck list depends only on the
        # format, not on the archetype contents, so reload decks only when the
        # (format, archetype names) signature actually changes — this collapses
        # the redundant second reload when the refresh returns identical data.
        signature = (self.current_format, tuple(a.get("name", "") for a in self.archetypes))
        if signature == self._last_archetype_reload_sig:
            logger.debug(
                "Archetypes unchanged for {fmt}; skipping redundant deck reload",
                fmt=self.current_format,
            )
            return
        self._last_archetype_reload_sig = signature
        self._load_decks(scope="all")

    def _on_archetypes_error(self: AppFrame, error: Exception) -> None:
        with self._loading_lock:
            self.loading_archetypes = False
        self.research_panel.set_error_state()
        self._set_status("app.status.archetypes_error", error=error)
        wx.MessageBox(
            f"Unable to load archetypes:\n{error}", "Archetype Error", wx.OK | wx.ICON_ERROR
        )

    def _on_decks_loaded(self: AppFrame, archetype_name: str, decks: list[dict[str, Any]]) -> None:
        with self._loading_lock:
            self.loading_decks = False
        self._all_loaded_decks = decks
        if self._is_first_deck_load:
            self._is_first_deck_load = False
            sm = self.controller.session_manager
            self.research_panel.set_event_type_filter(sm.get_deck_event_type_filter())
            self.research_panel.set_placement_filter(*sm.get_deck_placement_filter())
            self.research_panel.set_player_name_filter(sm.get_deck_player_filter())
            self.research_panel.set_date_filter(sm.get_deck_date_filter())
        else:
            self.research_panel.reset_event_type_filter()
            self.research_panel.reset_placement_filter()
            self.research_panel.reset_player_name_filter()
            self.research_panel.reset_date_filter()
        if not decks:
            self.controller.deck_repo.set_decks_list([])
            self.deck_list.Clear()
            self.deck_list.Append(self._t("deck_results.no_decks"))
            self.deck_list.Disable()
            self._set_status("deck_results.no_decks_for", archetype=archetype_name)
            self.summary_text.SetPage(
                simple_summary_html(f"{archetype_name}\n\nNo deck data available.")
            )
            return
        self._apply_deck_filters()
        self.daily_average_button.Enable()
        self._present_archetype_summary(archetype_name, decks)
        self._set_status(
            "deck_results.status.loaded_decks", count=len(decks), archetype=archetype_name
        )

    def _on_decks_error(self: AppFrame, error: Exception) -> None:
        with self._loading_lock:
            self.loading_decks = False
        self.deck_list.Clear()
        self.deck_list.Append(self._t("deck_results.failed_load"))
        self._set_status("app.status.decks_error", error=error)
        wx.MessageBox(f"Failed to load deck lists:\n{error}", "Deck Error", wx.OK | wx.ICON_ERROR)

    def _present_archetype_summary(
        self: AppFrame, archetype_name: str, decks: list[dict[str, Any]]
    ) -> None:
        total = len(decks)
        today = date.today()
        day_counts = []
        for days_ago in range(6, -1, -1):
            target = (today - timedelta(days=days_ago)).strftime("%Y-%m-%d")
            count = sum(1 for d in decks if d.get("date", "")[:10] == target)
            day_counts.append(str(count))
        per_day_str = "/".join(day_counts)
        name_escaped = (
            archetype_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        )
        if archetype_name == "Any":
            right_cell = ""
        else:
            right_cell = (
                '<td align="right" valign="middle">'
                f'<font size="3" color="#3B82F6"><b>{per_day_str}</b></font><br>'
                '<font size="2" color="#B9BFCA">last 7 days</font>'
                "</td>"
            )
        html = (
            '<html><body bgcolor="#22272E" text="#ECECEC">'
            '<table width="100%" cellpadding="5" cellspacing="0" bgcolor="#282E36">'
            "<tr>"
            "<td valign=middle>"
            f'<font size="4"><b>{name_escaped}</b></font><br>'
            f'<font size="2" color="#B9BFCA">{total} decks</font>'
            "</td>"
            f"{right_cell}"
            "</tr>"
            "</table>"
            "</body></html>"
        )
        self.summary_text.SetPage(html)

    def _load_decks(
        self: AppFrame,
        *,
        scope: str,
        archetype: dict[str, Any] | None = None,
    ) -> None:
        if scope == "all":
            name = "Any"
        elif scope == "archetype" and archetype is not None:
            name = archetype.get("name", "Unknown")
        else:
            wx.MessageBox("Archetype missing.", "Deck Error", wx.OK | wx.ICON_ERROR)
            return

        # Debounce rapid duplicate loads: the same target (scope + format +
        # name) firing twice within 1s is always redundant — e.g. the
        # stale-while-revalidate double archetype delivery, or a flurry of
        # selection events. Distinct targets are never debounced, so genuine
        # navigation (format switch, archetype click) stays responsive.
        signature = (scope, self.current_format, name)
        now = time.monotonic()
        if signature == self._last_deck_load_sig and (now - self._last_deck_load_time) < 1.0:
            logger.debug("Debouncing duplicate deck load: {sig}", sig=signature)
            return
        self._last_deck_load_sig = signature
        self._last_deck_load_time = now

        self._all_loaded_decks = []
        if not self._is_first_deck_load:
            self.research_panel.reset_event_type_filter()
            self.research_panel.reset_placement_filter()
            self.research_panel.reset_player_name_filter()
            self.research_panel.reset_date_filter()

        self.deck_list.Clear()
        self.deck_list.Append("Loading…")
        self.deck_list.Disable()
        self.summary_text.SetPage(simple_summary_html(f"{name}\n\nFetching deck results…"))

        self.controller.load_decks(
            scope=scope,
            archetype=archetype,
            on_success=lambda archetype_name, decks: wx.CallAfter(
                self._on_decks_loaded, archetype_name, decks
            ),
            on_error=lambda error: wx.CallAfter(self._on_decks_error, error),
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
        )
