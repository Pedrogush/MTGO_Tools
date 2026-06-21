"""Toolbar settings menu builders and preference setters for :class:`AppFrame`."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import wx

from utils.i18n import LOCALE_LABELS
from widgets.dialogs.image_download_dialog import show_image_download_dialog

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class ToolbarMenuHandlers(_Base):
    """Toolbar overflow menu and the preference setters its entries invoke.

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
                self,
                self.image_cache,
                self.image_downloader,
                self.controller.BULK_DATA_CACHE,
                self._set_status,
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
        self._append_menu_item(
            menu,
            self._t("toolbar.comp_rules"),
            self._open_rules_browser,
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
