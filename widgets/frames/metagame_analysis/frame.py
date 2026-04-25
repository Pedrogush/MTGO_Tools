"""UI construction for the metagame analysis viewer."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import wx
import wx.html
from loguru import logger
from matplotlib.backends.backend_wxagg import FigureCanvasWxAgg as FigureCanvas
from matplotlib.figure import Figure

from utils.constants import DARK_ALT, DARK_BG, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.i18n import translate
from widgets.frames.metagame_analysis.handlers import MetagameAnalysisHandlersMixin
from widgets.frames.metagame_analysis.properties import MetagameAnalysisPropertiesMixin


class MetagameAnalysisFrame(
    MetagameAnalysisHandlersMixin, MetagameAnalysisPropertiesMixin, wx.Frame
):
    """Widget for displaying metagame archetype distribution and changes over time."""

    def __init__(self, parent: wx.Window | None = None, locale: str | None = None) -> None:
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.metagame_analysis"),
            size=(980, 660),
            style=style,
        )
        self._locale = locale

        self.current_format: str = "modern"
        self.current_days: int = 1
        self.base_day_offset: int = 0
        self.current_data: dict[str, int] = {}
        self.previous_data: dict[str, int] = {}
        self.stats_data: dict[str, object] = {}

        self.min_days: int = 1
        self.max_days: int = 7
        self.max_day_offset: int = 30

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
        main_sizer.Add(toolbar, 0, wx.LEFT | wx.RIGHT | wx.TOP | wx.EXPAND, 8)

        format_label = wx.StaticText(panel, label=self._t("metagame.label.format"))
        format_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(format_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)
        self.format_choice = wx.Choice(
            panel,
            choices=[
                "Modern",
                "Standard",
                "Pioneer",
                "Legacy",
                "Vintage",
                "Pauper",
            ],
        )
        self.format_choice.SetSelection(0)
        self.format_choice.SetBackgroundColour(DARK_ALT)
        self.format_choice.SetForegroundColour(LIGHT_TEXT)
        self.format_choice.Bind(wx.EVT_CHOICE, self.on_format_change)
        toolbar.Add(self.format_choice, 0, wx.RIGHT, 12)

        time_window_label = wx.StaticText(panel, label=self._t("metagame.label.time_window"))
        time_window_label.SetForegroundColour(SUBDUED_TEXT)
        time_window_tooltip = self._t("metagame.tooltip.time_window")
        time_window_label.SetToolTip(time_window_tooltip)
        toolbar.Add(time_window_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.days_prev_button = wx.Button(panel, label="\u2190", size=(28, 26))
        self._stylize_button(self.days_prev_button)
        self.days_prev_button.Bind(wx.EVT_BUTTON, self.on_days_decrease)
        self.days_prev_button.SetToolTip(time_window_tooltip)
        toolbar.Add(self.days_prev_button, 0, wx.RIGHT, 3)

        self.days_value_box, self.days_value_label = self._create_value_badge(
            panel, str(self.current_days), tooltip=time_window_tooltip
        )
        toolbar.Add(self.days_value_box, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)

        self.days_next_button = wx.Button(panel, label="\u2192", size=(28, 26))
        self._stylize_button(self.days_next_button)
        self.days_next_button.Bind(wx.EVT_BUTTON, self.on_days_increase)
        self.days_next_button.SetToolTip(time_window_tooltip)
        toolbar.Add(self.days_next_button, 0, wx.RIGHT, 12)

        day_label = wx.StaticText(panel, label=self._t("metagame.label.starting_from"))
        day_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(day_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.offset_prev_button = wx.Button(panel, label="\u2190", size=(28, 26))
        self._stylize_button(self.offset_prev_button)
        self.offset_prev_button.Bind(wx.EVT_BUTTON, self.on_offset_decrease)
        toolbar.Add(self.offset_prev_button, 0, wx.RIGHT, 3)

        self.offset_value_box, self.offset_value_label = self._create_value_badge(
            panel, str(self.base_day_offset)
        )
        toolbar.Add(self.offset_value_box, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 3)

        self.offset_next_button = wx.Button(panel, label="\u2192", size=(28, 26))
        self._stylize_button(self.offset_next_button)
        self.offset_next_button.Bind(wx.EVT_BUTTON, self.on_offset_increase)
        toolbar.Add(self.offset_next_button, 0, wx.RIGHT, 12)

        self.refresh_button = wx.Button(panel, label=self._t("metagame.btn.refresh"))
        self._stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self.refresh_data())
        toolbar.Add(self.refresh_button, 0, wx.RIGHT, 8)

        toolbar.AddStretchSpacer(1)

        self.status_label = wx.StaticText(panel, label=self._t("app.status.ready"))
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(self.status_label, 0, wx.ALIGN_CENTER_VERTICAL)

        content_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(content_sizer, 1, wx.ALL | wx.EXPAND, 8)

        self.figure = Figure(figsize=(6, 5), facecolor="#14161b")
        self.canvas = FigureCanvas(panel, -1, self.figure)
        self.canvas.SetBackgroundColour(DARK_PANEL)
        content_sizer.Add(self.canvas, 1, wx.EXPAND | wx.RIGHT, 8)

        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor("#14161b")

        right_panel = wx.Panel(panel)
        right_panel.SetBackgroundColour(DARK_PANEL)
        right_panel.SetMinSize((250, -1))
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        right_panel.SetSizer(right_sizer)
        content_sizer.Add(right_panel, 0, wx.EXPAND)

        changes_label = wx.StaticText(right_panel, label=self._t("metagame.label.changes"))
        changes_label.SetForegroundColour(LIGHT_TEXT)
        font = changes_label.GetFont()
        font.MakeBold()
        font.PointSize += 2
        changes_label.SetFont(font)
        right_sizer.Add(changes_label, 0, wx.LEFT | wx.RIGHT | wx.TOP, 8)

        self.changes_html = wx.html.HtmlWindow(right_panel, style=wx.BORDER_NONE)
        self.changes_html.SetBackgroundColour(DARK_ALT)
        right_sizer.Add(self.changes_html, 1, wx.ALL | wx.EXPAND, 8)

        self._sync_navigation_controls()

    def _stylize_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _create_value_badge(
        self, parent: wx.Window, value: str, *, tooltip: str | None = None
    ) -> tuple[wx.Panel, wx.StaticText]:
        badge = wx.Panel(parent, size=(34, 24))
        badge.SetBackgroundColour(DARK_ALT)
        sizer = wx.BoxSizer(wx.VERTICAL)
        badge.SetSizer(sizer)

        sizer.AddStretchSpacer(1)
        label = wx.StaticText(badge, label=value, style=wx.ALIGN_CENTER_HORIZONTAL)
        label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL)
        sizer.AddStretchSpacer(1)

        if tooltip:
            badge.SetToolTip(tooltip)
            label.SetToolTip(tooltip)
        return badge, label


def main() -> None:
    """Launch the metagame analysis widget as a standalone application."""
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = MetagameAnalysisFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()
