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

from utils.constants import SPACE_MD, SPACE_SM, SPACE_XS
from utils.constants.theme import (
    SURFACE_ALT,
    SURFACE_BASE,
    SURFACE_PANEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from utils.i18n import translate
from widgets.frames.match_history.handlers import MatchHistoryHandlersMixin
from widgets.frames.match_history.properties import MatchHistoryPropertiesMixin
from widgets.input_frame import create_text_input
from widgets.section import SectionPanel
from widgets.stylize import (
    apply_type_level,
    create_divider,
    create_status_label,
    init_top_level_window,
    stylize_button,
    stylize_label,
    stylize_tree_list,
)

# These were five wx.Colour literals holding a byte-for-byte copy of the
# surface and text scales -- a second palette that happened to agree with
# theme.py and would have stopped agreeing the first time a token moved.
# Phase 0's whole point is that there is one source; phase 6b's sweep found
# this was the only file in widgets/ still carrying its own.
DARK_BG = wx.Colour(*SURFACE_BASE)
DARK_PANEL = wx.Colour(*SURFACE_PANEL)
DARK_ALT = wx.Colour(*SURFACE_ALT)
LIGHT_TEXT = wx.Colour(*TEXT_PRIMARY)
SUBDUED_TEXT = wx.Colour(*TEXT_SECONDARY)


class MatchHistoryFrame(MatchHistoryHandlersMixin, MatchHistoryPropertiesMixin, wx.Frame):
    """Simple window displaying recent MTGO matches grouped by event."""

    _FIXED_WIDTH = 850
    _COL_WIDTHS = [100, 90, 140]  # Result, Mulligans, Date (pixels)

    def __init__(
        self,
        parent: wx.Window | None = None,
        controller=None,
        locale: str | None = None,
    ) -> None:
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.match_history"),
            size=(self._FIXED_WIDTH, 460),
            style=style,
        )
        init_top_level_window(self)
        self._locale = locale
        self.controller = controller
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
        sizer.Add(toolbar, 0, wx.ALL | wx.EXPAND, SPACE_SM)

        self.refresh_button = wx.Button(panel, label=self._t("match.btn.refresh"))
        self._stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self.refresh_history())
        toolbar.Add(self.refresh_button, 0)

        # F8: the label takes the slack the stretch spacer used to, so it has a
        # bounded box to ellipsise inside instead of overflowing the window edge.
        self.status_label = create_status_label(panel, self._t("app.status.ready"))
        toolbar.Add(self.status_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, SPACE_SM)

        metrics_section = SectionPanel(
            panel, title=self._t("match.metrics.title"), padding=SPACE_SM
        )
        metrics_sizer = metrics_section.sizer
        box_parent = metrics_section.body
        sizer.Add(metrics_section, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, SPACE_SM)

        # Phase 5: the eight metrics were eight plain "Label: value" strings, so
        # every value started at a different x -- the label length decided where
        # the number went, and comparing two rates meant reading rather than
        # scanning. They are now a key/value grid: two pairs per row, labels
        # left, values on a shared right edge per column.
        metrics_inner = wx.FlexGridSizer(cols=4, gap=(SPACE_MD, SPACE_XS))
        metrics_inner.AddGrowableCol(1, 1)
        metrics_inner.AddGrowableCol(3, 1)
        metrics_sizer.Add(metrics_inner, 0, wx.EXPAND)

        self.match_rate_label = self._add_metric(
            metrics_inner, box_parent, "match.metrics.abs_match_rate"
        )
        self.game_rate_label = self._add_metric(
            metrics_inner, box_parent, "match.metrics.abs_game_rate"
        )
        self.filtered_match_rate_label = self._add_metric(
            metrics_inner, box_parent, "match.metrics.filtered_match_rate"
        )
        self.filtered_game_rate_label = self._add_metric(
            metrics_inner, box_parent, "match.metrics.filtered_game_rate"
        )
        self.mulligan_rate_label = self._add_metric(
            metrics_inner, box_parent, "match.metrics.mulligan_rate"
        )
        self.avg_mulligans_label = self._add_metric(
            metrics_inner, box_parent, "match.metrics.avg_mulligans"
        )

        metrics_sizer.Add(
            create_divider(box_parent, vertical=False), 0, wx.EXPAND | wx.TOP, SPACE_SM
        )

        # The opponent pair used to be secondary-coloured with nothing to say
        # why. They are scoped to whichever match is selected rather than to the
        # whole history, so they now sit under a heading that says so and the
        # colour has a stated meaning.
        self.opp_heading = wx.StaticText(box_parent, label=self._t("match.metrics.opp_none"))
        self.opp_heading.SetForegroundColour(SUBDUED_TEXT)
        apply_type_level(self.opp_heading, "caption")
        metrics_sizer.Add(self.opp_heading, 0, wx.TOP, SPACE_SM)

        opp_grid = wx.FlexGridSizer(cols=4, gap=(SPACE_MD, SPACE_XS))
        opp_grid.AddGrowableCol(1, 1)
        opp_grid.AddGrowableCol(3, 1)
        metrics_sizer.Add(opp_grid, 0, wx.EXPAND | wx.TOP, SPACE_XS)
        self.opp_match_rate_label = self._add_metric(
            opp_grid, box_parent, "match.metrics.opp_match_rate", secondary=True
        )
        self.opp_mull_rate_label = self._add_metric(
            opp_grid, box_parent, "match.metrics.opp_mull_rate", secondary=True
        )

        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        metrics_sizer.Add(filter_row, 0, wx.EXPAND | wx.TOP, SPACE_SM)
        filter_row.Add(
            self._filter_label(box_parent, "match.filter.start"),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            SPACE_XS,
        )
        start_field = create_text_input(box_parent, size=(120, -1))
        self.start_date_ctrl = start_field.ctrl
        filter_row.Add(start_field, 0, wx.RIGHT, SPACE_SM)
        filter_row.Add(
            self._filter_label(box_parent, "match.filter.end"),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            SPACE_XS,
        )
        end_field = create_text_input(box_parent, size=(120, -1))
        self.end_date_ctrl = end_field.ctrl
        filter_row.Add(end_field, 0, wx.RIGHT, SPACE_SM)
        apply_btn = wx.Button(box_parent, label=self._t("match.filter.apply"))
        stylize_button(apply_btn, kind="secondary", surface="panel")
        apply_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._update_metrics())
        filter_row.Add(apply_btn, 0)
        filter_row.AddStretchSpacer(1)

        self.tree = dv.TreeListCtrl(panel, style=dv.TL_DEFAULT_STYLE | dv.TL_SINGLE)
        self.tree.AppendColumn(self._t("match.col.players"), width=380)
        self.tree.AppendColumn(self._t("match.col.result"), width=100)
        self.tree.AppendColumn(self._t("match.col.mulligans"), width=90)
        self.tree.AppendColumn(self._t("match.col.date"), width=140)
        # After the columns exist, so the native header child is there to theme.
        # This site used to set the background and stop there, which left every
        # row of match text painting in wx's default black; the wrapper/inner
        # split that made that easy to miss now lives in one helper.
        stylize_tree_list(self.tree)
        self.tree.Bind(dv.EVT_TREELIST_ITEM_ACTIVATED, self.on_item_activated)
        self.tree.Bind(dv.EVT_TREELIST_SELECTION_CHANGED, self.on_item_selected)
        sizer.Add(self.tree, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, SPACE_SM)

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

    def _add_metric(
        self,
        sizer: wx.FlexGridSizer,
        parent: wx.Window,
        key: str,
        *,
        secondary: bool = False,
    ) -> wx.StaticText:
        """Add one label/value pair to a key/value grid, returning the value.

        The value control is right-aligned inside a growable column, which is
        what puts every number in the column on one edge. It needs
        ``wx.ST_NO_AUTORESIZE`` to stay that way: without it ``SetLabel``
        resizes the control to the new string and the alignment has nothing to
        align within (phase 4's finding, applied here).
        """
        colour = SUBDUED_TEXT if secondary else LIGHT_TEXT
        label = wx.StaticText(parent, label=self._t(key))
        label.SetForegroundColour(colour)
        sizer.Add(label, 0, wx.ALIGN_CENTER_VERTICAL)

        value = wx.StaticText(
            parent,
            label="\u2014",
            style=wx.ALIGN_RIGHT | wx.ST_NO_AUTORESIZE,
        )
        value.SetForegroundColour(colour)
        sizer.Add(value, 1, wx.EXPAND | wx.ALIGN_CENTER_VERTICAL)
        return value

    def _filter_label(self, parent: wx.Window, key: str) -> wx.StaticText:
        """A date-filter caption, themed like the metric labels beside it.

        These two were the only ``wx.StaticText``\\ s in the window built inline
        with no ``SetForegroundColour``, so they rendered in wx's default black
        on ``SURFACE_PANEL`` (1.53:1) while every label around them was
        ``TEXT_PRIMARY``. Routed through the helper so a third one cannot be
        added without a colour.
        """
        label = wx.StaticText(parent, label=self._t(key))
        stylize_label(label, level="body", surface="panel", tone="primary")
        return label

    def _stylize_button(self, button: wx.Button) -> None:
        stylize_button(button, kind="secondary")


def main() -> None:
    """Launch the match history viewer as a standalone application."""
    from controllers.app_controller import get_deck_selector_controller
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = MatchHistoryFrame(controller=get_deck_selector_controller())
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
