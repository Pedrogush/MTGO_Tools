"""Inspector preview + printing-selection handlers (issue #792)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class CardInspectorPreviewHandlers(_Base):
    """Drive the inspector/card-panel preview and printing-art selection."""

    def _handle_card_focus(self: AppFrame, zone: str, card: dict[str, Any] | None) -> None:
        if card is None:
            if self.card_inspector_panel.active_zone == zone:
                self.card_inspector_panel.reset()
                self.card_panel.clear()
            return
        if zone in {"main", "side"}:
            self._active_deck_zone = zone
        if self.builder_panel:
            self.builder_panel.clear_result_selection()
        self._collapse_other_zone_tables(zone)
        meta = self.controller.card_repo.get_card_metadata(card["name"])
        selection = self._printing_selections.get(card["name"].lower())
        self.card_inspector_panel.update_card(card, zone=zone, meta=meta, selection=selection)
        self._push_card_panel(card, meta)

    # ---- printing selection (issue #792) --------------------------------------
    def _get_printing_image(self: AppFrame, name: str):
        """Resolve the chosen printing's board image for ``name``.

        Returns the cached image path for the card's selected printing, or
        ``None`` when no printing is selected (board falls back to the default
        art) or its image is not cached yet — in which case a download for that
        exact printing is queued so a later ``refresh_card_image`` picks it up.
        Runs on the view's image-decode threads; only SQLite reads + an enqueue.
        """
        selection = self._printing_selections.get(name.lower())
        if not selection:
            return None
        uuid = selection.get("uuid")
        set_code = selection.get("set")
        cache = self.controller.get_image_cache()
        path = cache.get_image_by_uuid(uuid, "normal") if uuid else None
        if path is None and set_code:
            path = cache.get_image_path_for_printing(name, set_code, "normal")
        if path is not None:
            return path
        try:
            request = self.controller.CardImageRequest(
                card_name=name,
                uuid=uuid,
                set_code=set_code,
                collector_number=None,
                size="normal",
            )
            self.controller.image_service.queue_card_image_download(request, prioritize=True)
        except Exception:
            logger.debug("Failed to queue printing image for %s", name, exc_info=True)
        return None

    def _on_inspector_printing_selected(
        self: AppFrame, printing: dict[str, Any], persist: bool
    ) -> None:
        """Apply (and optionally persist) a printing the user chose in the inspector.

        Always updates the runtime selection map + board art (issue #792, part
        1a); ``persist`` also writes the choice into the deck text so it survives
        save/copy (part 2 — auto-save or the Save-art button).
        """
        name = self.card_inspector_panel.inspector_current_card_name
        if not name or not printing:
            return
        self._record_printing_selection(name, printing)
        if persist:
            self._persist_printing_selection(name, printing)

    def _refresh_board_card_art(self: AppFrame, name: str) -> None:
        """Re-render just ``name``'s art across every zone after a selection change."""
        for table in (self.main_table, self.side_table, self.out_table):
            if table:
                table.refresh_card_image(name)

    def _record_printing_selection(self: AppFrame, name: str, printing: dict[str, Any]) -> None:
        """Update the runtime selection map and refresh that card's board art."""
        if not name:
            return
        self._printing_selections[name.lower()] = {
            "uuid": printing.get("id"),
            "set": printing.get("set"),
        }
        self._refresh_board_card_art(name)

    def _persist_printing_selection(self: AppFrame, name: str, printing: dict[str, Any]) -> None:
        """Write a printing choice into the canonical deck text so it survives.

        Saving / copying the deck reads ``current_deck_text`` (see
        ``build_deck_text``), so merging the chosen printing-id pointer there is
        what makes the choice persist into the exported decklist (issue #792,
        part 2). No-op when the printing index has not loaded.
        """
        if not name:
            return
        index = getattr(self.controller.image_service, "bulk_data_by_name", None)
        if not index:
            return
        deck_text = self.controller.deck_repo.get_current_deck_text()
        if not deck_text or not deck_text.strip():
            return
        merged = self.controller.deck_service.merge_printing_selection(
            deck_text, index, name, printing.get("id"), printing.get("set")
        )
        self.controller.deck_repo.set_current_deck_text(merged)

    def _handle_card_hover(self: AppFrame, zone: str, card: dict[str, Any]) -> None:
        if self._has_selected_card():
            return
        self._pending_hover = (zone, card)
        if self._inspector_hover_timer is None:
            self._inspector_hover_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_hover_preview, self._inspector_hover_timer)
        elif self._inspector_hover_timer.IsRunning():
            self._inspector_hover_timer.Stop()
        # Debounce inspector updates to avoid thrashing while the mouse moves quickly.
        self._inspector_hover_timer.StartOnce(120)

    def _flush_hover_preview(self: AppFrame, _event: wx.TimerEvent) -> None:
        if not self._pending_hover:
            return
        if self._has_selected_card():
            self._pending_hover = None
            return
        zone, card = self._pending_hover
        self._pending_hover = None
        meta = self.controller.card_repo.get_card_metadata(card["name"])
        selection = self._printing_selections.get(card["name"].lower())
        self.card_inspector_panel.update_card(card, zone=zone, meta=meta, selection=selection)
        self._push_card_panel(card, meta)

    def _push_card_panel(self: AppFrame, card: dict[str, Any], meta: Any) -> None:
        """Forward the current card+printing+context to :attr:`card_panel`."""
        printing = self._current_inspector_printing()
        # Pass meta verbatim — both dicts and ``CardEntry`` work with the
        # panel's renderer (it only uses ``.get(key)``).
        self.card_panel.update_card(meta, printing=printing)

    def _current_inspector_printing(self: AppFrame) -> dict[str, Any] | None:
        printings = getattr(self.card_inspector_panel, "inspector_printings", None) or []
        idx = getattr(self.card_inspector_panel, "inspector_current_printing", 0)
        if not printings:
            return None
        try:
            entry = printings[idx]
        except IndexError:
            return None
        # Entries may be msgspec PrintingEntry structs or plain dicts.
        if isinstance(entry, dict):
            return entry
        if hasattr(entry, "get"):
            keys = (
                "id",
                "set",
                "set_name",
                "collector_number",
                "released_at",
                "flavor_text",
                "artist",
            )
            return {key: entry.get(key) for key in keys}
        return None
