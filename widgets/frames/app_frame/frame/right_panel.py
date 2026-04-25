"""Right column construction (toolbar, card inspector, oracle text) for :class:`AppFrame`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_PANEL, LIGHT_TEXT, PADDING_SM
from widgets.buttons.toolbar_buttons import ToolbarButtons
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.mana_rich_text_ctrl import ManaSymbolRichCtrl

if TYPE_CHECKING:
    from controllers.app_controller import AppController
    from utils.mana_icon_factory import ManaIconFactory


class RightPanelBuilderMixin:
    """Builds the toolbar plus the inspector column (card inspector + oracle text).

    The toolbar lives at the top of the right-side container, while the
    inspector and oracle text panels make up the rightmost column under it.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    controller: AppController
    mana_icons: ManaIconFactory
    toolbar: ToolbarButtons
    card_inspector_panel: CardInspectorPanel
    oracle_text_ctrl: ManaSymbolRichCtrl
    image_cache: object
    image_downloader: object

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

    def _build_oracle_text_panel(self, parent: wx.Window) -> wx.StaticBoxSizer:
        oracle_box = wx.StaticBox(parent, label=self._t("app.label.oracle_text"))
        oracle_box.SetForegroundColour(LIGHT_TEXT)
        oracle_box.SetBackgroundColour(DARK_PANEL)
        oracle_sizer = wx.StaticBoxSizer(oracle_box, wx.VERTICAL)

        self.oracle_text_ctrl = ManaSymbolRichCtrl(
            oracle_box,
            self.mana_icons,
            readonly=True,
            multiline=True,
        )
        self.oracle_text_ctrl.SetMinSize((-1, 200))

        oracle_sizer.Add(self.oracle_text_ctrl, 1, wx.EXPAND | wx.ALL, PADDING_SM)
        return oracle_sizer
