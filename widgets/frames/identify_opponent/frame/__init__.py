"""wxPython MTGO opponent tracker overlay UI construction package.

The :class:`MTGOpponentDeckSpy` frame owns the overall window state and
orchestrates the layout, while each builder mixin (:mod:`header`,
:mod:`calculator_panel`) is responsible for constructing a specific section.

Re-exports :class:`_LoadArchetypeDialog` so existing
``from widgets.frames.identify_opponent.frame import _LoadArchetypeDialog``
import sites continue to work.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path when the file is run directly
# (e.g. `python widgets/frames/identify_opponent/frame/__init__.py`).  Has no
# effect when the package is imported normally or via the installed console
# script.
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import wx
from loguru import logger

from repositories.metagame_repository import (
    MetagameRepository,
    get_metagame_repository,
)
from services.radar_service import RadarData, RadarService, get_radar_service
from utils.background_worker import BackgroundWorker
from utils.constants import (
    DARK_BG,
    OPPONENT_TRACKER_CACHE_TTL_SECONDS,
    OPPONENT_TRACKER_FRAME_SIZE,
    OPPONENT_TRACKER_LEFT_SASH_POS,
    OPPONENT_TRACKER_POLL_INTERVAL_MS,
    OPPONENT_TRACKER_SECTION_PADDING,
)
from utils.i18n import translate
from widgets.frames.identify_opponent.frame.calculator_panel import CalculatorPanelBuilderMixin
from widgets.frames.identify_opponent.frame.header import HeaderBuilderMixin
from widgets.frames.identify_opponent.frame.load_archetype_dialog import _LoadArchetypeDialog
from widgets.frames.identify_opponent.handlers import (
    MTGOpponentDeckSpyHandlersMixin,
)
from widgets.frames.identify_opponent.properties import (
    MTGOpponentDeckSpyPropertiesMixin,
)
from widgets.panels.compact_radar_panel import CompactRadarPanel
from widgets.panels.compact_sideboard_panel import CompactSideboardPanel


class MTGOpponentDeckSpy(
    MTGOpponentDeckSpyHandlersMixin,
    MTGOpponentDeckSpyPropertiesMixin,
    HeaderBuilderMixin,
    CalculatorPanelBuilderMixin,
    wx.Frame,
):
    """Always-on-top overlay that detects opponents from MTGO window titles."""

    CACHE_TTL = OPPONENT_TRACKER_CACHE_TTL_SECONDS
    POLL_INTERVAL_MS = OPPONENT_TRACKER_POLL_INTERVAL_MS

    def __init__(
        self,
        parent: wx.Window | None = None,
        radar_service: RadarService | None = None,
        metagame_repository: MetagameRepository | None = None,
        locale: str | None = None,
    ) -> None:
        style = (
            wx.CAPTION | wx.CLOSE_BOX | wx.STAY_ON_TOP | wx.FRAME_FLOAT_ON_PARENT | wx.MINIMIZE_BOX
        )
        super().__init__(
            parent,
            title=translate(locale, "window.title.opponent_tracker"),
            size=OPPONENT_TRACKER_FRAME_SIZE,
            style=style,
        )

        self._locale = locale
        self._poll_timer = wx.Timer(self)

        self.cache: dict[str, dict[str, Any]] = {}
        self.player_name: str = ""
        self.last_seen_decks: dict[str, str] = {}  # format -> deck name

        self._saved_position: list[int] | None = None

        # Background poll worker
        self._bg_worker = BackgroundWorker()
        self._poll_generation: int = 0
        self._poll_in_progress: bool = False
        self._watching_enabled: bool = True
        self._manual_archetype_loaded: bool = False

        # Radar integration
        self.radar_service: RadarService = radar_service or get_radar_service()
        self.metagame_repo: MetagameRepository = metagame_repository or get_metagame_repository()
        self.current_radar: RadarData | None = None
        self._radar_worker_thread: threading.Thread | None = None
        self._radar_cancel_requested: bool = False
        self._last_radar_archetype: str = ""

        # Sideboard guide integration
        self._last_guide_archetype: str = ""

        self._load_cache()
        self._load_config()

        self._build_ui()
        self._apply_window_preferences()

        self.Bind(wx.EVT_TIMER, self._on_poll_tick, self._poll_timer)
        self.Bind(wx.EVT_CLOSE, self.on_close)

        wx.CallAfter(self._start_polling)

    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        outer_sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(outer_sizer)

        self._build_header(panel, outer_sizer)
        self._build_main_area(panel, outer_sizer)

    def _build_main_area(self, panel: wx.Panel, outer_sizer: wx.Sizer) -> None:
        """Compose the main two-panel area: left splitter (calc/radar) and right sideboard."""
        main_sizer = wx.BoxSizer(wx.HORIZONTAL)
        outer_sizer.Add(
            main_sizer,
            1,
            wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM,
            OPPONENT_TRACKER_SECTION_PADDING,
        )

        # Left panel: vertical splitter — Calc (top) / Radar (bottom)
        self._left_splitter = wx.SplitterWindow(panel, style=wx.SP_3D | wx.SP_LIVE_UPDATE)
        self._left_splitter.SetBackgroundColour(DARK_BG)
        main_sizer.Add(
            self._left_splitter, 0, wx.RIGHT | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING
        )

        self._build_calculator_panel(self._left_splitter)

        self.radar_panel = CompactRadarPanel(self._left_splitter)
        self.radar_panel.clear()  # show placeholder (does not hide in new layout)

        self._left_splitter.SplitHorizontally(
            self.calc_panel, self.radar_panel, OPPONENT_TRACKER_LEFT_SASH_POS
        )
        self._left_splitter.SetMinimumPaneSize(80)
        self._left_splitter.SetSashGravity(0.0)
        wx.CallAfter(self._fit_left_splitter)

        # Right panel: Sideboard Guide
        self.sideboard_panel = CompactSideboardPanel(panel)
        self.sideboard_panel.set_no_pinned_deck()
        main_sizer.Add(self.sideboard_panel, 1, wx.EXPAND)


def main() -> None:
    """Launch the opponent tracker as a standalone application."""
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = MTGOpponentDeckSpy()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()


__all__ = ["MTGOpponentDeckSpy", "_LoadArchetypeDialog", "main"]
