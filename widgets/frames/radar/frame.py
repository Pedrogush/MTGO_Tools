"""UI construction for the archetype radar panel and standalone frame."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import wx
import wx.dataview as dv

from services.radar_service import RadarData, RadarService, get_radar_service
from utils.constants import DARK_ALT, DARK_PANEL, LIGHT_TEXT
from utils.i18n import translate
from widgets.frames.radar.handlers import RadarFrameHandlersMixin, RadarPanelHandlersMixin
from widgets.frames.radar.properties import RadarFramePropertiesMixin, RadarPanelPropertiesMixin


class RadarPanel(RadarPanelHandlersMixin, RadarPanelPropertiesMixin, wx.Panel):
    """Panel that displays archetype radar (card frequency analysis)."""

    def __init__(
        self,
        parent: wx.Window,
        radar_service: RadarService | None = None,
        on_export: Callable[[RadarData], None] | None = None,
        on_use_for_search: Callable[[RadarData], None] | None = None,
        locale: str | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale

        self.radar_service = radar_service or get_radar_service()
        self.on_export = on_export
        self.on_use_for_search = on_use_for_search
        self.current_radar: RadarData | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        header_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(header_sizer, 0, wx.EXPAND | wx.ALL, 6)

        self.archetype_label = wx.StaticText(self, label=self._t("radar.label.no_radar"))
        self.archetype_label.SetForegroundColour(LIGHT_TEXT)
        font = self.archetype_label.GetFont()
        font.PointSize += 2
        font = font.Bold()
        self.archetype_label.SetFont(font)
        header_sizer.Add(self.archetype_label, 1, wx.ALIGN_CENTER_VERTICAL)

        self.export_btn = wx.Button(self, label=self._t("radar.btn.export"))
        self.export_btn.Enable(False)
        self.export_btn.Bind(wx.EVT_BUTTON, self._on_export_clicked)
        header_sizer.Add(self.export_btn, 0, wx.LEFT, 6)

        self.use_search_btn = wx.Button(self, label=self._t("radar.btn.use_search"))
        self.use_search_btn.Enable(False)
        self.use_search_btn.Bind(wx.EVT_BUTTON, self._on_use_search_clicked)
        header_sizer.Add(self.use_search_btn, 0, wx.LEFT, 6)

        self.summary_label = wx.StaticText(self, label="")
        self.summary_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.summary_label, 0, wx.ALL, 6)

        split_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(split_sizer, 1, wx.EXPAND | wx.ALL, 6)

        mainboard_box = wx.StaticBox(self, label=self._t("radar.box.mainboard"))
        mainboard_box.SetForegroundColour(LIGHT_TEXT)
        mainboard_box_sizer = wx.StaticBoxSizer(mainboard_box, wx.VERTICAL)
        split_sizer.Add(mainboard_box_sizer, 1, wx.EXPAND | wx.RIGHT, 6)

        self.mainboard_list = dv.DataViewListCtrl(self)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.card"), width=200)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.inclusion"), width=90)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.expected"), width=120)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.avg"), width=90)
        self.mainboard_list.AppendTextColumn(self._t("radar.col.max"), width=60)
        self.mainboard_list.SetBackgroundColour(DARK_ALT)
        self.mainboard_list.SetForegroundColour(LIGHT_TEXT)
        self._bind_tooltip_handlers(self.mainboard_list)
        mainboard_box_sizer.Add(self.mainboard_list, 1, wx.EXPAND | wx.ALL, 6)

        sideboard_box = wx.StaticBox(self, label=self._t("radar.box.sideboard"))
        sideboard_box.SetForegroundColour(LIGHT_TEXT)
        sideboard_box_sizer = wx.StaticBoxSizer(sideboard_box, wx.VERTICAL)
        split_sizer.Add(sideboard_box_sizer, 1, wx.EXPAND)

        self.sideboard_list = dv.DataViewListCtrl(self)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.card"), width=200)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.inclusion"), width=90)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.expected"), width=120)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.avg"), width=90)
        self.sideboard_list.AppendTextColumn(self._t("radar.col.max"), width=60)
        self.sideboard_list.SetBackgroundColour(DARK_ALT)
        self.sideboard_list.SetForegroundColour(LIGHT_TEXT)
        self._bind_tooltip_handlers(self.sideboard_list)
        sideboard_box_sizer.Add(self.sideboard_list, 1, wx.EXPAND | wx.ALL, 6)


class RadarFrame(RadarFrameHandlersMixin, RadarFramePropertiesMixin, wx.Frame):
    """Standalone window for generating and viewing archetype radars."""

    def __init__(
        self,
        parent: wx.Window | None = None,
        metagame_repo: Any = None,
        format_name: str = "",
        radar_service: RadarService | None = None,
        on_use_for_search: Callable[[RadarData], None] | None = None,
        locale: str | None = None,
    ):
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.radar", format=format_name),
            size=(900, 700),
            style=style,
        )
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale

        self.metagame_repo = metagame_repo
        self.format_name = format_name
        self.radar_service = radar_service or get_radar_service()
        self._on_use_for_search_cb = on_use_for_search
        self.archetypes: list[dict[str, Any]] = []
        self.current_radar: RadarData | None = None
        self.worker_thread: threading.Thread | None = None
        self.cancel_requested = False

        self._build_ui()
        self._load_archetypes()
        self.Centre(wx.BOTH)

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        selection_sizer = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(selection_sizer, 0, wx.EXPAND | wx.ALL, 10)

        label = wx.StaticText(panel, label=self._t("radar.dialog.select_archetype"))
        label.SetForegroundColour(LIGHT_TEXT)
        selection_sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)

        self.archetype_choice = wx.Choice(panel)
        self.archetype_choice.SetBackgroundColour(DARK_ALT)
        self.archetype_choice.SetForegroundColour(LIGHT_TEXT)
        selection_sizer.Add(self.archetype_choice, 1, wx.RIGHT, 6)

        self.generate_btn = wx.Button(panel, label=self._t("radar.dialog.generate"))
        self.generate_btn.Bind(wx.EVT_BUTTON, self._on_generate_clicked)
        selection_sizer.Add(self.generate_btn, 0, wx.RIGHT, 6)

        self.cancel_btn = wx.Button(panel, label=self._t("radar.btn.cancel"))
        self.cancel_btn.Bind(wx.EVT_BUTTON, self._on_cancel_clicked)
        self.cancel_btn.Enable(False)
        selection_sizer.Add(self.cancel_btn, 0)

        self.progress = wx.Gauge(panel, range=100)
        sizer.Add(self.progress, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

        self.progress_label = wx.StaticText(panel, label="")
        self.progress_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.progress_label, 0, wx.ALL, 10)

        self.radar_panel = RadarPanel(
            panel,
            radar_service=self.radar_service,
            on_export=self._export_radar,
            on_use_for_search=self._use_radar_for_search,
            locale=self._locale,
        )
        sizer.Add(self.radar_panel, 1, wx.EXPAND | wx.ALL, 10)

        self.Bind(wx.EVT_CLOSE, self._on_close)
