"""Event handlers, menu builders, session/window persistence, and deck rendering for the main application frame."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.card_images import CardImageRequest
from utils.constants import APP_FRAME_MIN_SIZE
from utils.i18n import LOCALE_LABELS
from utils.runtime_flags import is_automation_enabled
from widgets.dialogs.help_dialog import show_help
from widgets.dialogs.image_download_dialog import show_image_download_dialog
from widgets.dialogs.tutorial_dialog import show_tutorial
from widgets.frames.app_frame.handlers.app_events import _simple_summary_html
from widgets.frames.mana_keyboard import open_mana_keyboard

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class AppFrameHandlersMixin(_Base):
    """Menu, session, window, filter, and deck-rendering handlers for :class:`AppFrame`.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    def _open_toolbar_settings_menu(self, anchor: wx.Window) -> None:
        menu = wx.Menu()
        self._append_menu_item(
            menu,
            self._t("toolbar.load_collection"),
            lambda: self.controller.refresh_collection_from_bridge(force=True),
        )
        self._append_menu_item(
            menu,
            self._t("toolbar.download_card_images"),
            lambda: show_image_download_dialog(
                self, self.image_cache, self.image_downloader, self._set_status
            ),
        )
        self._append_menu_item(
            menu,
            self._t("toolbar.update_card_database"),
            lambda: self.controller.force_bulk_data_update(),
        )
        self._append_menu_item(
            menu,
            self._t("toolbar.export_diagnostics"),
            self._open_feedback_dialog,
        )
        self._append_menu_item(
            menu,
            self._t("toolbar.show_tutorial"),
            self._open_tutorial,
        )
        self._append_menu_item(
            menu,
            self._t("toolbar.help"),
            self._open_help,
        )
        menu.AppendSeparator()
        self._append_radio_submenu(
            menu,
            self._t("app.menu.deck_data_source"),
            (
                ("both", self._t("app.choice.source.both")),
                ("mtggoldfish", self._t("app.choice.source.mtggoldfish")),
                ("mtgo", self._t("app.choice.source.mtgo")),
            ),
            current_value=self.controller.get_deck_data_source(),
            on_select=self._apply_deck_source,
        )
        self._append_radio_submenu(
            menu,
            self._t("app.menu.language"),
            tuple((locale, LOCALE_LABELS[locale]) for locale in self._language_values),
            current_value=self.locale,
            on_select=self._apply_language,
        )
        self._append_radio_submenu(
            menu,
            self._t("app.menu.average_method"),
            (
                ("karsten", self._t("app.choice.average_method.karsten")),
                ("arithmetic", self._t("app.choice.average_method.arithmetic")),
            ),
            current_value=self.controller.get_average_method(),
            on_select=self._apply_average_method,
        )
        self._append_radio_submenu(
            menu,
            self._t("app.menu.average_hours"),
            tuple(
                (str(h), self._t(f"app.choice.average_hours.{h}")) for h in (12, 24, 36, 48, 60, 72)
            ),
            current_value=str(self.controller.get_average_hours()),
            on_select=lambda v: self._apply_average_hours(int(v)),
        )
        anchor.PopupMenu(menu)
        menu.Destroy()

    def _append_menu_item(
        self, menu: wx.Menu, label: str, handler: Callable[[], None]
    ) -> wx.MenuItem:
        item = menu.Append(wx.ID_ANY, label)
        menu.Bind(wx.EVT_MENU, lambda _evt, cb=handler: cb(), item)
        return item

    def _append_radio_submenu(
        self,
        menu: wx.Menu,
        label: str,
        options: tuple[tuple[str, str], ...],
        *,
        current_value: str,
        on_select: Callable[[str], None],
    ) -> None:
        submenu = wx.Menu()
        for value, item_label in options:
            item = submenu.AppendRadioItem(wx.ID_ANY, item_label)
            item.Check(value == current_value)
            submenu.Bind(wx.EVT_MENU, lambda _evt, selected=value, cb=on_select: cb(selected), item)
        menu.AppendSubMenu(submenu, label)

    def _apply_deck_source(self, source: str) -> None:
        self.controller.set_deck_data_source(source)
        self._schedule_settings_save()

    def _apply_language(self, locale: str) -> None:
        self.locale = locale
        self.controller.set_language(locale)
        self._set_status("app.status.language_changed")
        self._schedule_settings_save()

    def _apply_average_method(self, method: str) -> None:
        self.controller.set_average_method(method)
        self._schedule_settings_save()

    def _apply_average_hours(self, hours: int) -> None:
        self.controller.set_average_hours(hours)
        self._schedule_settings_save()

    def _handle_image_downloaded(self, request: CardImageRequest) -> None:
        self.card_inspector_panel.handle_image_downloaded(request)
        self.main_table.refresh_card_image(request.card_name)
        self.side_table.refresh_card_image(request.card_name)
        if self.out_table:
            self.out_table.refresh_card_image(request.card_name)

    # ------------------------------------------------------------------ Left panel helpers -------------------------------------------------
    def _show_left_panel(self, mode: str, force: bool = False) -> None:
        target = "builder" if mode == "builder" else "research"
        if self.left_stack:
            index = 1 if target == "builder" else 0
            if force or self.left_stack.GetSelection() != index:
                self.left_stack.ChangeSelection(index)
        if target == "builder":
            self.ensure_card_data_loaded()
        if force or self.left_mode != target:
            self.left_mode = target
            self._schedule_settings_save()

    def _open_full_mana_keyboard(self) -> None:
        self.mana_keyboard_window = open_mana_keyboard(
            self, self.mana_icons, self.mana_keyboard_window, self._on_mana_keyboard_closed
        )

    def _open_tutorial(self) -> None:
        show_tutorial(self, locale=self.locale)
        self.controller.session_manager.mark_tutorial_shown()

    def _open_help(self, topic: str | None = None) -> None:
        show_help(self, topic=topic)

    def _restore_session_state(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)
        if not self.controller.session_manager.is_tutorial_shown() and not is_automation_enabled():
            wx.CallAfter(self._open_tutorial)

        # Restore left panel mode
        self._show_left_panel(state["left_mode"], force=True)

        has_saved_deck = bool(state.get("zone_cards"))

        # Restore zone cards
        if has_saved_deck:
            if self.controller.card_repo.is_card_data_ready():
                self._render_current_deck()
            else:
                self._pending_deck_restore = True
                self._set_status("app.status.restoring_deck")
                self.ensure_card_data_loaded()

        # Restore deck text
        if (
            state.get("deck_text")
            and self.controller.card_repo.is_card_data_ready()
            and not has_saved_deck
        ):
            self._update_stats(state["deck_text"])
            self.copy_button.Enable(True)
            self.save_button.Enable(True)
            self.deck_notes_panel.load_notes_for_current()
            self._load_guide_for_current()

    # ------------------------------------------------------------------ Window persistence ---------------------------------------------------
    def _save_window_settings(self) -> None:
        pos = self.GetPosition()
        size = self.GetSize()
        self.controller.save_settings(
            window_size=(size.width, size.height), screen_pos=(pos.x, pos.y)
        )

    def _apply_window_preferences(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)

        # Apply window size
        if "window_size" in state:
            try:
                width, height = state["window_size"]
                self.SetSize(wx.Size(int(width), int(height)))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window size")

        # Apply window position
        if "screen_pos" in state:
            try:
                x, y = state["screen_pos"]
                self.SetPosition(wx.Point(int(x), int(y)))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window position")

    def _apply_min_size(self) -> None:
        if not self.root_panel or not self.root_panel.GetSizer():
            self.SetMinSize(APP_FRAME_MIN_SIZE)
            return
        self.root_panel.Layout()
        min_size = self.root_panel.GetSizer().GetMinSize()
        try:
            min_size = self.ClientToWindowSize(min_size)
        except AttributeError:
            pass
        self.SetMinSize(
            wx.Size(
                max(APP_FRAME_MIN_SIZE[0], min_size.GetWidth()),
                max(APP_FRAME_MIN_SIZE[1], min_size.GetHeight()),
            )
        )

    def _schedule_settings_save(self) -> None:
        if self._save_timer is None:
            self._save_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_pending_settings, self._save_timer)
        if self._save_timer.IsRunning():
            self._save_timer.Stop()
        self._save_timer.StartOnce(600)

    def _flush_pending_settings(self, _event: wx.TimerEvent) -> None:
        self._save_window_settings()

    def _schedule_filter_debounce(self) -> None:
        if self._filter_debounce_timer is None:
            self._filter_debounce_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_deck_filters, self._filter_debounce_timer)
        if self._filter_debounce_timer.IsRunning():
            self._filter_debounce_timer.Stop()
        self._filter_debounce_timer.StartOnce(250)

    def _flush_deck_filters(self, _event: wx.TimerEvent) -> None:
        self._apply_deck_filters()

    def fetch_archetypes(self, force: bool = False) -> None:
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
        self.summary_text.SetPage(_simple_summary_html(self._t("app.status.select_archetype")))
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
