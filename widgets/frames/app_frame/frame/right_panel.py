"""Right column construction (toolbar, card inspector, card panel) for :class:`AppFrame`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_PANEL, LIGHT_TEXT, PADDING_SM
from widgets.buttons.toolbar_buttons import ToolbarButtons
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_panel import CardPanel

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class RightPanelBuilderMixin(_Base):
    """Builds the toolbar plus the inspector column (card inspector + oracle text).

    The toolbar lives at the top of the right-side container, while the
    inspector and oracle text panels make up the rightmost column under it.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    def _build_toolbar(self, parent: wx.Window) -> ToolbarButtons:
        return ToolbarButtons(
            parent,
            on_open_opponent_tracker=self.open_opponent_tracker,
            on_open_timer_alert=self.open_timer_alert,
            on_open_match_history=self.open_match_history,
            on_open_metagame_analysis=self.open_metagame_analysis,
            on_open_top_cards=self.open_top_cards,
            on_open_radar=self.open_radar,
            on_open_settings_menu=self._open_toolbar_settings_menu,
            labels={
                "opponent_tracker": self._t("toolbar.opponent_tracker"),
                "timer_alert": self._t("toolbar.timer_alert"),
                "match_history": self._t("toolbar.match_history"),
                "metagame_analysis": self._t("toolbar.metagame_analysis"),
                "top_cards": self._t("toolbar.top_cards"),
                "radar": self._t("toolbar.radar"),
                "settings": "\u2699",
                "settings_tooltip": self._t("toolbar.settings"),
                "opponent_tracker_tooltip": self._t("toolbar.tooltip.opponent_tracker"),
                "timer_alert_tooltip": self._t("toolbar.tooltip.timer_alert"),
                "match_history_tooltip": self._t("toolbar.tooltip.match_history"),
                "metagame_analysis_tooltip": self._t("toolbar.tooltip.metagame_analysis"),
                "top_cards_tooltip": self._t("toolbar.tooltip.top_cards"),
                "radar_tooltip": self._t("toolbar.tooltip.radar"),
            },
        )

    def _build_card_inspector(self, parent: wx.Window) -> wx.StaticBoxSizer:
        inspector_box = wx.StaticBox(parent, label=self._t("app.label.card_inspector"))
        inspector_box.SetForegroundColour(LIGHT_TEXT)
        inspector_box.SetBackgroundColour(DARK_PANEL)
        inspector_sizer = wx.StaticBoxSizer(inspector_box, wx.VERTICAL)

        self.card_inspector_panel = CardInspectorPanel(
            inspector_box,
            card_manager=self.controller.card_repo.get_card_manager(),
            mana_icons=self.mana_icons,
        )
        self.card_inspector_panel.set_image_request_handlers(
            on_request=lambda request: self.controller.image_service.queue_card_image_download(
                request, prioritize=True
            ),
            on_selected=self.controller.image_service.set_selected_card_request,
        )
        self.card_inspector_panel.set_printings_request_handler(
            self.controller.image_service.fetch_printings_by_name_async
        )
        self.controller.image_service.set_image_download_callback(self._handle_image_downloaded)
        self.controller.image_service.set_printings_loaded_callback(
            self.card_inspector_panel.handle_printings_loaded
        )
        inspector_sizer.Add(self.card_inspector_panel, 1, wx.EXPAND)
        inspector_sizer.Layout()
        inspector_min_size = inspector_sizer.GetMinSize()
        inspector_box.SetMinSize(inspector_min_size)

        # Keep backward compatibility references (delegate to image service via controller)
        self.image_cache = self.controller.image_service.image_cache
        self.image_downloader = self.controller.image_service.image_downloader

        return inspector_sizer

    def _build_card_panel(self, parent: wx.Window) -> wx.StaticBoxSizer:
        card_box = wx.StaticBox(parent, label=self._t("app.label.card_panel"))
        card_box.SetForegroundColour(LIGHT_TEXT)
        card_box.SetBackgroundColour(DARK_PANEL)
        card_sizer = wx.StaticBoxSizer(card_box, wx.VERTICAL)

        self.card_panel = CardPanel(
            card_box,
            mana_icons=self.mana_icons,
            t=self._t,
        )
        self.card_panel.SetMinSize((-1, 240))

        # Mirror printing changes (caused by prev/next clicks or async loads)
        # from the inspector into the card panel so flavor/artist/edition stay
        # in sync with the printing actually shown.
        self.card_inspector_panel.set_printing_changed_handler(self.card_panel.update_printing)

        card_sizer.Add(self.card_panel, 1, wx.EXPAND | wx.ALL, PADDING_SM)
        return card_sizer
