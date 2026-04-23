"""UI construction for the match history viewer."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from typing import Any

import wx
import wx.dataview as dv
from loguru import logger

from utils.i18n import translate
from widgets.frames.match_history.handlers import MatchHistoryHandlersMixin
from widgets.frames.match_history.properties import MatchHistoryPropertiesMixin

DARK_BG = wx.Colour(20, 22, 27)
DARK_PANEL = wx.Colour(34, 39, 46)
DARK_ALT = wx.Colour(40, 46, 54)
LIGHT_TEXT = wx.Colour(236, 236, 236)
SUBDUED_TEXT = wx.Colour(185, 191, 202)


class MatchHistoryFrame(MatchHistoryHandlersMixin, MatchHistoryPropertiesMixin, wx.Frame):
    """Simple window displaying recent MTGO matches grouped by event."""

    _FIXED_WIDTH = 850
    _COL_WIDTHS = [100, 90, 140]  # Result, Mulligans, Date (pixels)

    def __init__(self, parent: wx.Window | None = None, locale: str | None = None) -> None:
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.match_history"),
            size=(self._FIXED_WIDTH, 460),
            style=style,
        )
        self._locale = locale
        # Lock horizontal size; allow vertical resize only
        self.SetSizeHints(self._FIXED_WIDTH, 300, self._FIXED_WIDTH, -1)

        self.history_items: list[dict[str, Any]] = []
        self.start_filter: str | None = None
        self.end_filter: str | None = None
        self.current_username: str | None = None

        self._build_ui()
        self.Centre(wx.BOTH)
        self.Bind(wx.EVT_SIZE, self._on_frame_size)

        self.Bind(wx.EVT_CLOSE, self.on_close)
        wx.CallAfter(self._fit_tree_columns)
        wx.CallAfter(self._init_username)
        wx.CallAfter(self.refresh_history)

    # ------------------------------------------------------------------ UI build
    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(toolbar, 0, wx.ALL | wx.EXPAND, 10)

        self.refresh_button = wx.Button(panel, label=self._t("match.btn.refresh"))
        self._stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self.refresh_history())
        toolbar.Add(self.refresh_button, 0)

        toolbar.AddStretchSpacer(1)

        self.status_label = wx.StaticText(panel, label=self._t("app.status.ready"))
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(self.status_label, 0, wx.ALIGN_CENTER_VERTICAL)

        metrics_box = wx.StaticBox(panel, label=self._t("match.metrics.title"))
        metrics_box.SetForegroundColour(LIGHT_TEXT)
        metrics_box.SetBackgroundColour(DARK_PANEL)
        metrics_sizer = wx.StaticBoxSizer(metrics_box, wx.VERTICAL)
        box_parent = metrics_sizer.GetStaticBox()
        sizer.Add(metrics_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 6)

        metrics_inner = wx.BoxSizer(wx.VERTICAL)
        metrics_sizer.Add(metrics_inner, 0, wx.EXPAND | wx.ALL, 8)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.match_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.abs_match_rate')}: \u2014"
        )
        self.match_rate_label.SetForegroundColour(LIGHT_TEXT)
        row1.Add(self.match_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.game_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.abs_game_rate')}: \u2014"
        )
        self.game_rate_label.SetForegroundColour(LIGHT_TEXT)
        row1.Add(self.game_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row1, 0, wx.EXPAND | wx.BOTTOM, 4)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.filtered_match_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.filtered_match_rate')}: \u2014"
        )
        self.filtered_match_rate_label.SetForegroundColour(LIGHT_TEXT)
        row2.Add(self.filtered_match_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.filtered_game_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.filtered_game_rate')}: \u2014"
        )
        self.filtered_game_rate_label.SetForegroundColour(LIGHT_TEXT)
        row2.Add(self.filtered_game_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row2, 0, wx.EXPAND | wx.BOTTOM, 4)

        row3 = wx.BoxSizer(wx.HORIZONTAL)
        self.mulligan_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.mulligan_rate')}: \u2014"
        )
        self.mulligan_rate_label.SetForegroundColour(LIGHT_TEXT)
        row3.Add(self.mulligan_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.avg_mulligans_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.avg_mulligans')}: \u2014"
        )
        self.avg_mulligans_label.SetForegroundColour(LIGHT_TEXT)
        row3.Add(self.avg_mulligans_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row3, 0, wx.EXPAND)

        metrics_inner.Add(wx.StaticLine(box_parent), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 6)

        row_opp = wx.BoxSizer(wx.HORIZONTAL)
        self.opp_match_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.opp_match_rate')}: \u2014"
        )
        self.opp_match_rate_label.SetForegroundColour(SUBDUED_TEXT)
        row_opp.Add(self.opp_match_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.opp_mull_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.opp_mull_rate')}: \u2014"
        )
        self.opp_mull_rate_label.SetForegroundColour(SUBDUED_TEXT)
        row_opp.Add(self.opp_mull_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row_opp, 0, wx.EXPAND)

        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        metrics_sizer.Add(filter_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        filter_row.Add(
            wx.StaticText(box_parent, label=self._t("match.filter.start")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            4,
        )
        self.start_date_ctrl = wx.TextCtrl(box_parent, size=(120, -1))
        self.start_date_ctrl.SetBackgroundColour(DARK_ALT)
        self.start_date_ctrl.SetForegroundColour(LIGHT_TEXT)
        filter_row.Add(self.start_date_ctrl, 0, wx.RIGHT, 10)
        filter_row.Add(
            wx.StaticText(box_parent, label=self._t("match.filter.end")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            4,
        )
        self.end_date_ctrl = wx.TextCtrl(box_parent, size=(120, -1))
        self.end_date_ctrl.SetBackgroundColour(DARK_ALT)
        self.end_date_ctrl.SetForegroundColour(LIGHT_TEXT)
        filter_row.Add(self.end_date_ctrl, 0, wx.RIGHT, 10)
        apply_btn = wx.Button(box_parent, label=self._t("match.filter.apply"))
        apply_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._update_metrics())
        filter_row.Add(apply_btn, 0)
        filter_row.AddStretchSpacer(1)

        self.tree = dv.TreeListCtrl(panel, style=dv.TL_DEFAULT_STYLE | dv.TL_SINGLE)
        self.tree.SetBackgroundColour(DARK_ALT)
        self.tree.AppendColumn(self._t("match.col.players"), width=380)
        self.tree.AppendColumn(self._t("match.col.result"), width=100)
        self.tree.AppendColumn(self._t("match.col.mulligans"), width=90)
        self.tree.AppendColumn(self._t("match.col.date"), width=140)
        self.tree.Bind(dv.EVT_TREELIST_ITEM_ACTIVATED, self.on_item_activated)
        self.tree.Bind(dv.EVT_TREELIST_SELECTION_CHANGED, self.on_item_selected)
        sizer.Add(self.tree, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

    def _on_frame_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        wx.CallAfter(self._fit_tree_columns)

    def _fit_tree_columns(self) -> None:
        if not self.tree:
            return
        dv_ctrl = self.tree.GetDataView()
        tree_w = self.tree.GetClientSize().width
        scrollbar_w = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        # Column 0 in the DataViewCtrl is the internal tree-expander column;
        # our first user column (Players) is at index 1.
        expander_w = dv_ctrl.GetColumn(0).GetWidth()
        col0_w = tree_w - expander_w - sum(self._COL_WIDTHS) - scrollbar_w
        if col0_w > 80:
            dv_ctrl.GetColumn(1).SetWidth(col0_w)

    def _stylize_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)


def main() -> None:
    """Launch the match history viewer as a standalone application."""
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = MatchHistoryFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
