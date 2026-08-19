"""Right column construction (the card inspector) for :class:`AppFrame`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import SPACE_SM, SPACE_XS
from utils.perf import timed
from widgets.panels.card_inspector_panel import CardInspectorPanel
from widgets.panels.card_panel import CardPanel
from widgets.section import SectionPanel

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class RightPanelBuilderMixin(_Base):
    """Builds the inspector column: one card, one card panel (§4.6).

    Until phase 7 this was **two** section cards stacked, ``Card Inspector``
    (image + printing pager) over ``Card`` (Oracle Text / Stats tabs). They are
    two views of one object, both write the card's name into themselves, and
    neither name says which is which — the review's §4.6. They are now one
    section with an internal hierarchy: the card's own art on top, then the tab
    strip for everything the art cannot show.

    That also settles a measurement phase 6 left open. Phase 6 (#971) recorded
    the both-panels-expanded minimum height rising 902 → 918 because *two* real
    headings replaced two ``wx.StaticBox`` grooves, and said "phase 7 merges
    those two panels and gets it back". One heading is now gone, along with the
    second card's border, padding and the gap between the two.

    The toolbar that used to sit above this column became the window-wide menu
    bar in phase 3b (see :mod:`widgets.menu_bar`).

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    @timed
    def _build_card_inspector(self, parent: wx.Window) -> SectionPanel:
        section = SectionPanel(parent, title=self._t("app.label.card_inspector"), padding=SPACE_XS)

        self.card_inspector_panel = CardInspectorPanel(
            section.body,
            controller=self.controller,
            card_manager=self.controller.card_repo.get_card_manager(),
            mana_icons=self.mana_icons,
            locale=self.locale,
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
        # Proportion 0: the art, its pager and the save-art row are a fixed
        # block (CardInspectorPanel pins its own min/max height), so the tabs
        # below take every leftover pixel rather than the two fighting for them.
        section.sizer.Add(self.card_inspector_panel, 0, wx.EXPAND)

        # Keep backward compatibility references (delegate to image service via controller)
        self.image_cache = self.controller.image_service.image_cache
        self.image_downloader = self.controller.image_service.image_downloader

        self._build_card_panel(section)

        return section

    @timed
    def _build_card_panel(self, section: SectionPanel) -> None:
        """The Oracle Text / Stats tabs, inside the inspector's one section card.

        A second heading here was what §4.6 objected to: "Card" named the same
        object as "Card Inspector" 400px above it. The tab strip is the label
        this content needs — the same reasoning phase 6 used when it dropped the
        deck workspace's "Deck Workspace" heading for the tab strip beneath it.
        """
        self.card_panel = CardPanel(
            section.body,
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

        section.sizer.Add(self.card_panel, 1, wx.EXPAND | wx.TOP, SPACE_SM)
