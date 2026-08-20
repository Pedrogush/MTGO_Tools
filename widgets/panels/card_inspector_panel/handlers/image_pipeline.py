"""Async image-lookup pipeline for the card inspector panel.

The background-thread image-path lookup (with a generation counter to discard
stale results from rapid card switches), the UI-thread appliers, the inbound
download/printings callbacks, and the display-mode/selection helpers.
"""

from __future__ import annotations

from pathlib import Path
from threading import Thread
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from services.deck_service.printing import selected_printing_index
from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from services.image_service import CardImageRequest
    from widgets.panels.card_inspector_panel.protocol import CardInspectorPanelProto

    _Base = CardInspectorPanelProto
else:
    _Base = object


class ImagePipelineMixin(_Base):
    """Async image lookup, inbound image/printings callbacks, and display mode."""

    def handle_image_downloaded(self, request: CardImageRequest) -> None:
        self._failed_image_requests.discard(self._failure_key(request))
        if not self.inspector_current_card_name:
            return
        if not self._request_matches_current(request):
            return
        self._load_current_printing_image()

    def handle_image_download_failed(self, request: CardImageRequest, _message: str) -> None:
        self._failed_image_requests.add(self._failure_key(request))
        if not self.inspector_current_card_name:
            return
        if not self._request_matches_current(request):
            return
        self._loading_printing = False
        self._set_display_mode(self._image_available)

    def handle_printings_loaded(self, card_name: str, printings: list[dict[str, Any]]) -> None:
        if not self.inspector_current_card_name:
            return
        if card_name.lower() != self.inspector_current_card_name.lower():
            return
        self._printings_request_inflight = None
        if not printings:
            return
        self.inspector_printings = printings
        self.inspector_current_printing = selected_printing_index(
            printings, self.inspector_selection
        )
        self._emit_printing_changed()
        self._load_current_printing_image()

    def _load_card_image_and_printings(self, card_name: str) -> None:
        self.inspector_current_card_name = card_name
        self.inspector_printings = []
        self.inspector_current_printing = 0
        self._printings_request_inflight = None
        self._loading_printing = False

        # Query in-memory bulk data for all printings
        if self.bulk_data_by_name:
            printings = self.bulk_data_by_name.get(card_name.lower(), [])
            self.inspector_printings = printings
            # Open on the card's saved printing rather than the list head (#792).
            self.inspector_current_printing = selected_printing_index(
                printings, self.inspector_selection
            )
        elif self.controller.BULK_DATA_CACHE.exists():
            logger.debug(f"Bulk data not loaded yet for {card_name}")

        # Load the image
        self._load_current_printing_image()

    def _load_current_printing_image(self) -> None:
        """Start an async image-path lookup, then apply results on the UI thread.

        SQLite queries run in a background thread to avoid blocking the event loop.
        A generation counter ensures stale results from rapid card switches are discarded.
        """
        self._image_lookup_gen += 1
        gen = self._image_lookup_gen

        # Snapshot all state needed by the background thread.
        printings = list(self.inspector_printings)
        current_idx = self.inspector_current_printing
        card_name = self.inspector_current_card_name
        image_request_name = self._image_request_name
        image_cache = self.image_cache

        # Build active_request now — no I/O required.
        active_request: CardImageRequest | None = None
        if not printings:
            if card_name:
                active_request = self.controller.CardImageRequest(
                    card_name=image_request_name or card_name,
                    uuid=None,
                    set_code=None,
                    collector_number=None,
                    size="normal",
                )
        else:
            printing = printings[current_idx]
            uuid = printing.get("id")
            active_request = self.controller.CardImageRequest(
                card_name=image_request_name or card_name or "",
                uuid=uuid,
                set_code=printing.get("set"),
                collector_number=printing.get("collector_number"),
                size="normal",
            )

        def _lookup() -> None:
            if not printings:
                path = self.controller.get_card_image(card_name, "normal") if card_name else None
                if not path and image_request_name:
                    path = self.controller.get_card_image(image_request_name, "normal")
                wx.CallAfter(self._apply_no_printings_image, gen, card_name, active_request, path)
            else:
                uuid = active_request.uuid if active_request else None
                image_paths = image_cache.get_image_paths_by_uuid(uuid, "normal") if uuid else []
                name_printing_path = None
                if not image_paths and active_request and active_request.set_code:
                    name_printing_path = image_cache.get_image_path_for_printing(
                        active_request.card_name, active_request.set_code, active_request.size
                    )
                wx.CallAfter(
                    self._apply_printings_image,
                    gen,
                    printings,
                    current_idx,
                    active_request,
                    image_paths,
                    name_printing_path,
                )

        Thread(target=_lookup, daemon=True).start()

    def _apply_no_printings_image(
        self,
        gen: int,
        card_name: str | None,
        active_request: CardImageRequest | None,
        image_path: Path | None,
    ) -> None:
        if gen != self._image_lookup_gen:
            return
        image_available = False
        if image_path and image_path.exists():
            image_available = self.card_image_display.show_image(image_path)
        else:
            self.card_image_display.show_placeholder("Not cached")
            if card_name and active_request:
                if (
                    self._printings_request_handler
                    and self._printings_request_inflight != card_name.lower()
                ):
                    self._printings_request_inflight = card_name.lower()
                    self._printings_request_handler(card_name)
                    self._loading_printing = True
        self.nav_panel.Hide()
        self.save_panel.Hide()
        self._notify_selection(active_request)
        self._set_display_mode(image_available, show_image_column=image_available)
        if not image_available and active_request:
            self._request_missing_image(active_request)

    def _apply_printings_image(
        self,
        gen: int,
        printings: list[dict[str, Any]],
        current_idx: int,
        active_request: CardImageRequest | None,
        image_paths: list[Path],
        name_printing_path: Path | None,
    ) -> None:
        try:
            if not self:
                return
        except RuntimeError:
            return
        if gen != self._image_lookup_gen:
            return
        image_available = False
        if image_paths:
            if len(image_paths) > 1:
                image_available = self.card_image_display.show_images(image_paths)
            else:
                image_available = self.card_image_display.show_image(image_paths[0])
            self._loading_printing = not image_available
        elif name_printing_path and name_printing_path.exists():
            image_available = self.card_image_display.show_image(name_printing_path)
            self._loading_printing = not image_available
        else:
            self.card_image_display.show_placeholder("Not cached")
            self._loading_printing = True

        # Update navigation controls.
        printing = printings[current_idx]
        if len(printings) > 1:
            set_code = printing.get("set", "").upper()
            set_name = printing.get("set_name", "")
            printing_info = f"{current_idx + 1} of {len(printings)}"
            if set_code:
                printing_info += f" - {set_code}"
            if set_name:
                printing_info += f" ({set_name})"
            self._set_printing_label(printing_info)
            self.prev_btn.Enable(current_idx > 0)
            self.next_btn.Enable(current_idx < len(printings) - 1)
            self.nav_panel.Show()
            self.save_panel.Show()
        else:
            self.nav_panel.Hide()
            self.save_panel.Hide()

        self._notify_selection(active_request)
        self._set_display_mode(image_available)
        if not image_available:
            self._request_missing_image(active_request)

    def _set_display_mode(
        self, image_available: bool, *, show_image_column: bool | None = None
    ) -> None:
        self._image_available = image_available
        if show_image_column is None:
            show_image_column = image_available or bool(self.inspector_printings)
        self.image_column_panel.Show(show_image_column)
        self.card_image_display.Show(image_available)
        self.image_text_panel.Show(not image_available)
        if self._loading_printing:
            self.loading_label.Show()
        else:
            self.loading_label.Hide()
        show_details = self._has_selection and (not image_available or self._loading_printing)
        self.details_panel.Show(show_details)
        relayout(self)

    def _notify_selection(self, request: CardImageRequest | None) -> None:
        if self._selected_card_handler:
            self._selected_card_handler(request)

    def _request_missing_image(self, request: CardImageRequest | None) -> None:
        if request is None or not self._image_request_handler:
            return
        if self._failure_key(request) in self._failed_image_requests:
            return
        logger.debug(
            "Card inspector requesting image for %s (set=%s, size=%s, collector=%s).",
            request.card_name,
            request.set_code,
            request.size,
            request.collector_number,
        )
        self._image_request_handler(request)
