"""Deck-display rendering, archetype listing, and stats updates for :class:`AppFrame`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from widgets.frames.app_frame.handlers.deck_formatting import simple_summary_html

if TYPE_CHECKING:
    from services.image_service import CardImageRequest
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class DeckRenderHandlers(_Base):
    """Render the loaded deck into the tables/inspector and keep stats in sync.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    def _handle_image_downloaded(self, request: CardImageRequest) -> None:
        self.card_inspector_panel.handle_image_downloaded(request)
        self.main_table.refresh_card_image(request.card_name)
        self.side_table.refresh_card_image(request.card_name)
        if self.out_table:
            self.out_table.refresh_card_image(request.card_name)

    def fetch_archetypes(self, force: bool = False) -> None:
        if force:
            # An explicit reload must always refresh the deck list, even if the
            # refreshed archetype list is byte-for-byte identical. Clearing the
            # dedup signature lets _on_archetypes_loaded reload decks again.
            self._last_archetype_reload_sig = None
        self.research_panel.set_loading_state()
        self.controller.deck_repo.clear_decks_list()
        self.deck_list.Clear()
        self._clear_deck_display()
        self.daily_average_button.Disable()
        self.copy_button.Disable()
        self.save_button.Disable()

        self.controller.fetch_archetypes(
            on_success=lambda archetypes: wx.CallAfter(self._on_archetypes_loaded, archetypes),
            on_error=lambda error: wx.CallAfter(self._on_archetypes_error, error),
            on_status=lambda *a, **kw: wx.CallAfter(self._set_status, *a, **kw),
            force=force,
        )

    def _clear_deck_display(self) -> None:
        self.controller.deck_repo.set_current_deck(None)
        self.summary_text.SetPage(simple_summary_html(self._t("app.status.select_archetype")))
        self.zone_cards = {"main": [], "side": [], "out": []}
        self.main_table.set_cards([])
        self.side_table.set_cards([])
        if self.out_table:
            self.out_table.set_cards(self.zone_cards["out"])
        self.controller.deck_repo.set_current_deck_text("")
        self._update_stats("")
        self.deck_notes_panel.clear()
        self.sideboard_guide_panel.clear()
        self.card_inspector_panel.reset()
        self.card_panel.clear()

    def _render_current_deck(self) -> None:
        self.main_table.set_cards(self.zone_cards["main"])
        self.side_table.set_cards(self.zone_cards["side"])
        if self.out_table:
            self.out_table.set_cards(self.zone_cards["out"])
        deck_text = self.controller.deck_repo.get_current_deck_text()
        if deck_text:
            self._update_stats(deck_text)
            self.copy_button.Enable(True)
            self.save_button.Enable(True)
        self.deck_notes_panel.load_notes_for_current()
        self._load_guide_for_current()
        self._pending_deck_restore = False

    def _render_pending_deck(self) -> None:
        if not self.controller.card_repo.is_card_data_ready():
            return
        if self._pending_deck_restore or self._has_deck_loaded():
            self._render_current_deck()

    def _populate_archetype_list(self) -> None:
        archetype_names = ["Any"] + [
            item.get("name", "Unknown") for item in self.filtered_archetypes
        ]
        self.research_panel.populate_archetypes(archetype_names)

    def _on_deck_download_success(self, content: str) -> None:
        self.present_deck_text(content)

    def _update_stats(self, deck_text: str) -> None:
        self.deck_stats_panel.update_stats(deck_text, self.zone_cards)
