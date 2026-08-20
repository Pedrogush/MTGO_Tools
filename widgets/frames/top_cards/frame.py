"""UI construction for the Top Cards viewer."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import TYPE_CHECKING

import wx

from utils.constants import DARK_BG, FORMAT_OPTIONS, LIGHT_TEXT, SPACE_SM, SPACE_XS
from utils.constants.theme import TEXT_SECONDARY
from utils.constants.ui_layout import (
    TOP_CARDS_COL_ARCHETYPES_WIDTH,
    TOP_CARDS_COL_AVG_WIDTH,
    TOP_CARDS_COL_CARD_WIDTH,
    TOP_CARDS_COL_COPIES_WIDTH,
    TOP_CARDS_COL_DECKS_WIDTH,
    TOP_CARDS_COL_FORMATS_WIDTH,
    TOP_CARDS_COL_RANK_WIDTH,
    TOP_CARDS_FRAME_SIZE,
)
from utils.i18n import translate
from widgets.frames.top_cards.handlers import TopCardsHandlersMixin
from widgets.frames.top_cards.properties import TopCardsPropertiesMixin
from widgets.grids import DataGrid, GridColumn
from widgets.stylize import (
    apply_type_level,
    create_status_label,
    init_top_level_window,
    stylize_button,
    stylize_choice,
)

if TYPE_CHECKING:
    from services.format_card_pool_service import FormatCardPoolService
    from services.radar_service import RadarService

TOP_CARDS_EXCLUDED_FORMATS = {"Commander", "Brawl", "Historic"}
TOP_CARDS_FORMAT_OPTIONS = [
    option for option in FORMAT_OPTIONS if option not in TOP_CARDS_EXCLUDED_FORMATS
]


class TopCardsFrame(TopCardsHandlersMixin, TopCardsPropertiesMixin, wx.Frame):
    """Widget for browsing the most-played cards in each format."""

    def __init__(
        self,
        parent: wx.Window | None = None,
        controller=None,
        locale: str | None = None,
    ) -> None:
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.top_cards"),
            size=TOP_CARDS_FRAME_SIZE,
            style=style,
        )
        init_top_level_window(self)
        self._locale = locale
        self.controller = controller
        self._service: FormatCardPoolService = controller.format_card_pool_service
        self._radar_service: RadarService = controller.radar_service
        self.current_format = "modern"

        self._build_ui()
        self.Centre(wx.BOTH)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        wx.CallAfter(self.refresh_data)

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(main_sizer)

        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(toolbar, 0, wx.ALL | wx.EXPAND, SPACE_SM)

        label = wx.StaticText(panel, label=self._t("top_cards.label.format"))
        label.SetForegroundColour(LIGHT_TEXT)
        toolbar.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)

        self.format_choice = wx.Choice(panel, choices=TOP_CARDS_FORMAT_OPTIONS)
        self.format_choice.SetSelection(TOP_CARDS_FORMAT_OPTIONS.index("Modern"))
        stylize_choice(self.format_choice)
        self.format_choice.Bind(wx.EVT_CHOICE, self.on_format_change)
        toolbar.Add(self.format_choice, 0, wx.RIGHT, SPACE_SM)

        self.refresh_button = wx.Button(panel, label=self._t("top_cards.btn.refresh"))
        self._stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self.refresh_data())
        toolbar.Add(self.refresh_button, 0, wx.RIGHT, SPACE_SM)

        # F8: see create_status_label -- proportion 1 in place of the spacer.
        # This one started with an empty label, so its best size was ~0 wide and
        # the first SetLabel had nothing but slack to grow into.
        self.status_label = create_status_label(panel)
        toolbar.Add(self.status_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, SPACE_SM)

        # C9 / the review's alignment finding: this was a wx.ListCtrl with every
        # one of its eleven columns centred -- including all ten numeric ones,
        # which destroys digit alignment so 952 / 648 / 616 / 515 cannot be
        # compared by length. It is now an own-drawn grid: see
        # widgets/grids/data_grid.py for why the control had to change rather
        # than just its column formats.
        # The headers name two averages that differ by denominator; the tooltips
        # that explained them hang off the header HWND, which a mouse-motion
        # handler on the list body never sees. One always-visible line is the
        # cheaper and more reliable legend.
        self.legend_label = wx.StaticText(panel, label=self._t("top_cards.legend"))
        self.legend_label.SetForegroundColour(wx.Colour(*TEXT_SECONDARY))
        apply_type_level(self.legend_label, "caption")
        main_sizer.Add(self.legend_label, 0, wx.LEFT | wx.RIGHT, SPACE_SM)

        self.card_list = DataGrid(panel, surface="panel")
        self.card_list.set_columns(self._columns())
        main_sizer.Add(self.card_list, 1, wx.ALL | wx.EXPAND, SPACE_SM)

        self._bind_header_tooltips()

    def _columns(self) -> list[GridColumn]:
        """Column order, width and alignment.

        Every numeric column is right-aligned so the digits line up and a column
        can be read by length; ``Card`` and ``Formats`` are left-aligned text.
        ``Copies`` is the sort key, so it is wider than the columns beside it
        rather than sharing their near-uniform width.
        """
        right = wx.ALIGN_RIGHT
        left = wx.ALIGN_LEFT
        return [
            GridColumn(self._t("top_cards.col.rank"), TOP_CARDS_COL_RANK_WIDTH, right),
            GridColumn(self._t("top_cards.col.card"), TOP_CARDS_COL_CARD_WIDTH, left),
            GridColumn(self._t("top_cards.col.copies"), TOP_CARDS_COL_COPIES_WIDTH, right),
            GridColumn(self._t("top_cards.col.mb_decks"), TOP_CARDS_COL_DECKS_WIDTH, right),
            GridColumn(self._t("top_cards.col.mb_avg"), TOP_CARDS_COL_AVG_WIDTH, right),
            GridColumn(self._t("top_cards.col.mb_avg_karsten"), TOP_CARDS_COL_AVG_WIDTH, right),
            GridColumn(self._t("top_cards.col.sb_decks"), TOP_CARDS_COL_DECKS_WIDTH, right),
            GridColumn(self._t("top_cards.col.sb_avg"), TOP_CARDS_COL_AVG_WIDTH, right),
            GridColumn(self._t("top_cards.col.sb_avg_karsten"), TOP_CARDS_COL_AVG_WIDTH, right),
            GridColumn(self._t("top_cards.col.archetypes"), TOP_CARDS_COL_ARCHETYPES_WIDTH, right),
            GridColumn(self._t("top_cards.col.formats"), TOP_CARDS_COL_FORMATS_WIDTH, left),
        ]

    def _stylize_button(self, button: wx.Button) -> None:
        stylize_button(button, kind="secondary")
