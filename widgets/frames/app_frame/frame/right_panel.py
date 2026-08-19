"""Right column construction (card inspector, card panel) for :class:`AppFrame`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_PANEL, LIGHT_TEXT, SPACE_XS
from utils.perf import timed
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_panel import CardPanel

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class RightPanelBuilderMixin(_Base):
    """Builds the inspector column (card inspector + oracle text).

    The toolbar that used to sit above this column became the window-wide menu
    bar in phase 3b (see :mod:`widgets.menu_bar`).

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    @timed
    def _build_card_inspector(self, parent: wx.Window) -> wx.StaticBoxSizer:
        inspector_box = wx.StaticBox(parent, label=self._t("app.label.card_inspector"))
        inspector_box.SetForegroundColour(LIGHT_TEXT)
        inspector_box.SetBackgroundColour(DARK_PANEL)
        inspector_sizer = wx.StaticBoxSizer(inspector_box, wx.VERTICAL)

        self.card_inspector_panel = CardInspectorPanel(
            inspector_box,
            controller=self.controller,
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
        self.controller.image_service.set_image_download_failed_callback(
            self._handle_image_download_failed
        )
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

    @timed
    def _build_card_panel(self, parent: wx.Window) -> wx.StaticBoxSizer:
        card_box = wx.StaticBox(parent, label=self._t("app.label.card_panel"))
        card_box.SetForegroundColour(LIGHT_TEXT)
        card_box.SetBackgroundColour(DARK_PANEL)
        card_sizer = wx.StaticBoxSizer(card_box, wx.VERTICAL)

        self.card_panel = CardPanel(
            card_box,
            controller=self.controller,
            mana_icons=self.mana_icons,
            t=self._t,
        )
        self.card_panel.SetMinSize((-1, 240))

        # Mirror printing changes (caused by prev/next clicks or async loads)
        # from the inspector into the card panel so flavor/artist/edition stay
        # in sync with the printing actually shown.
        self.card_inspector_panel.set_printing_changed_handler(self.card_panel.update_printing)
        # Sync the board art to the printing the user scrolls to / saves, and
        # persist the choice when auto-save (or the Save-art button) asks (#792).
        self.card_inspector_panel.set_printing_selected_handler(
            self._on_inspector_printing_selected
        )

        card_sizer.Add(self.card_panel, 1, wx.EXPAND | wx.ALL, SPACE_XS)
        return card_sizer
