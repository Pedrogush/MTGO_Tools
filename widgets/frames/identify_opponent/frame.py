"""UI construction, dialog class, and standalone ``main`` entry point for the
wxPython MTGO opponent tracker overlay."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

# Ensure the project root is on sys.path when the file is run directly
# (e.g. `python widgets/frames/identify_opponent/frame.py`).  Has no effect when
# the package is imported normally or via the installed console script.
_project_root = Path(__file__).resolve().parent.parent.parent.parent
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
    CALC_ACTION_BUTTON_SPACING,
    CALC_BUTTON_GREEN,
    CALC_COPIES_DEFAULT,
    CALC_COPIES_MAX,
    CALC_DECK_SIZE_DEFAULT,
    CALC_DECK_SIZE_MAX,
    CALC_DECK_SIZE_MIN,
    CALC_DRAWN_DEFAULT,
    CALC_GRID_COLS,
    CALC_GRID_HGAP,
    CALC_GRID_ROWS,
    CALC_GRID_VGAP,
    CALC_PRESET_BUTTON_HEIGHT,
    CALC_PRESET_BUTTON_SPACING,
    CALC_PRESET_BUTTON_WIDTH,
    CALC_PRESET_OPEN_40_DECK,
    CALC_PRESET_OPEN_40_DRAWN,
    CALC_PRESET_OPEN_60_DECK,
    CALC_PRESET_OPEN_60_DRAWN,
    CALC_PRESET_T3_DRAW_DECK,
    CALC_PRESET_T3_DRAW_DRAWN,
    CALC_PRESET_T3_PLAY_DECK,
    CALC_PRESET_T3_PLAY_DRAWN,
    CALC_SECTION_PADDING,
    CALC_SPIN_WIDTH,
    CALC_TARGET_DEFAULT,
    DARK_BG,
    DARK_PANEL,
    FORMAT_OPTIONS,
    LIGHT_TEXT,
    OPPONENT_TRACKER_CACHE_TTL_SECONDS,
    OPPONENT_TRACKER_FRAME_SIZE,
    OPPONENT_TRACKER_LABEL_WRAP_WIDTH,
    OPPONENT_TRACKER_LEFT_SASH_POS,
    OPPONENT_TRACKER_POLL_INTERVAL_MS,
    OPPONENT_TRACKER_SECTION_PADDING,
    SUBDUED_TEXT,
)
from utils.i18n import translate
from widgets.frames.identify_opponent.handlers import (
    MTGOpponentDeckSpyHandlersMixin,
)
from widgets.frames.identify_opponent.properties import (
    MTGOpponentDeckSpyPropertiesMixin,
)
from widgets.panels.compact_radar_panel import CompactRadarPanel
from widgets.panels.compact_sideboard_panel import CompactSideboardPanel


class MTGOpponentDeckSpy(
    MTGOpponentDeckSpyHandlersMixin, MTGOpponentDeckSpyPropertiesMixin, wx.Frame
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

    # ------------------------------------------------------------------ UI ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.SetBackgroundColour(DARK_BG)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        outer_sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(outer_sizer)

        # --- Header: deck label, status, controls ---
        self.deck_label = wx.StaticText(panel, label=self._t("tracker.label.not_detected"))
        self._stylize_label(self.deck_label)
        self.deck_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        outer_sizer.Add(self.deck_label, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        self.status_label = wx.StaticText(panel, label=self._t("tracker.label.watching"))
        self._stylize_label(self.status_label, subtle=True)
        self.status_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        outer_sizer.Add(
            self.status_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            OPPONENT_TRACKER_SECTION_PADDING,
        )

        divider = wx.StaticLine(panel)
        outer_sizer.Add(
            divider, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING
        )

        controls = wx.BoxSizer(wx.HORIZONTAL)
        outer_sizer.Add(controls, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        controls.AddStretchSpacer(1)

        refresh_button = wx.Button(panel, label=self._t("tracker.btn.refresh"))
        self._stylize_secondary_button(refresh_button)
        refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self._manual_refresh(force=True))
        controls.Add(refresh_button, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        self.load_arch_btn = wx.Button(panel, label=self._t("tracker.btn.load_archetype"))
        self._stylize_secondary_button(self.load_arch_btn)
        self.load_arch_btn.Bind(wx.EVT_BUTTON, self._on_load_archetype_clicked)
        controls.Add(self.load_arch_btn, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        close_button = wx.Button(panel, label=self._t("tracker.btn.close"))
        self._stylize_secondary_button(close_button)
        close_button.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        controls.Add(close_button, 0)

        # --- Main two-panel area ---
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

    def _stylize_label(
        self, label: wx.StaticText, *, bold: bool = False, subtle: bool = False
    ) -> None:
        label.SetForegroundColour(SUBDUED_TEXT if subtle else LIGHT_TEXT)
        label.SetBackgroundColour(DARK_BG)
        font = label.GetFont()
        if bold:
            font.MakeBold()
            font.SetPointSize(font.GetPointSize() + 1)
        label.SetFont(font)

    def _stylize_secondary_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def _build_calculator_panel(self, parent: wx.Window) -> None:
        self.calc_panel = wx.Panel(parent)
        self.calc_panel.SetBackgroundColour(DARK_PANEL)

        calc_sizer = wx.BoxSizer(wx.VERTICAL)
        self.calc_panel.SetSizer(calc_sizer)

        # Title
        title = wx.StaticText(self.calc_panel, label="Hypergeometric Calculator")
        title.SetForegroundColour(LIGHT_TEXT)
        title_font = title.GetFont()
        title_font.MakeBold()
        title.SetFont(title_font)
        calc_sizer.Add(title, 0, wx.ALL, CALC_SECTION_PADDING)

        # Input grid
        grid = wx.FlexGridSizer(CALC_GRID_ROWS, CALC_GRID_COLS, CALC_GRID_VGAP, CALC_GRID_HGAP)
        calc_sizer.Add(grid, 0, wx.ALL | wx.EXPAND, CALC_SECTION_PADDING)

        # Deck Size
        lbl_deck = wx.StaticText(self.calc_panel, label="Deck Size:")
        lbl_deck.SetForegroundColour(LIGHT_TEXT)
        self.spin_deck_size = wx.SpinCtrl(
            self.calc_panel,
            min=CALC_DECK_SIZE_MIN,
            max=CALC_DECK_SIZE_MAX,
            initial=CALC_DECK_SIZE_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_deck_size.SetToolTip("Total cards in deck (N)")
        grid.Add(lbl_deck, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_deck_size, 0)

        # Copies in Deck
        lbl_copies = wx.StaticText(self.calc_panel, label="Copies in Deck:")
        lbl_copies.SetForegroundColour(LIGHT_TEXT)
        self.spin_copies = wx.SpinCtrl(
            self.calc_panel,
            min=0,
            max=CALC_COPIES_MAX,
            initial=CALC_COPIES_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_copies.SetToolTip("Number of target cards in deck (K)")
        grid.Add(lbl_copies, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_copies, 0)

        # Cards Drawn
        lbl_drawn = wx.StaticText(self.calc_panel, label="Cards Drawn:")
        lbl_drawn.SetForegroundColour(LIGHT_TEXT)
        self.spin_drawn = wx.SpinCtrl(
            self.calc_panel,
            min=0,
            max=CALC_COPIES_MAX,
            initial=CALC_DRAWN_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_drawn.SetToolTip("Number of cards drawn (n)")
        grid.Add(lbl_drawn, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_drawn, 0)

        # Target Copies
        lbl_target = wx.StaticText(self.calc_panel, label="Target Copies:")
        lbl_target.SetForegroundColour(LIGHT_TEXT)
        self.spin_target = wx.SpinCtrl(
            self.calc_panel,
            min=0,
            max=CALC_COPIES_MAX,
            initial=CALC_TARGET_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_target.SetToolTip("Desired number of target cards (k)")
        grid.Add(lbl_target, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_target, 0)

        # Button rows: Open 60 / Open 40 | T3 Play / T3 Draw | Calculate / Clear
        btn_size = (CALC_PRESET_BUTTON_WIDTH, CALC_PRESET_BUTTON_HEIGHT)

        def _make_preset_btn(label: str, deck: int, drawn: int) -> wx.Button:
            btn = wx.Button(self.calc_panel, label=label, size=btn_size)
            btn.SetBackgroundColour(DARK_BG)
            btn.SetForegroundColour(LIGHT_TEXT)
            btn.Bind(wx.EVT_BUTTON, lambda evt, d=deck, n=drawn: self._apply_preset(d, n))
            return btn

        def _centered_row(left: wx.Button, right: wx.Button, gap: int) -> wx.BoxSizer:
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.AddStretchSpacer(1)
            row.Add(left, 0, wx.RIGHT, gap)
            row.Add(right, 0)
            row.AddStretchSpacer(1)
            return row

        # Row 1: Open 60 | Open 40
        open60 = _make_preset_btn("Open 60", CALC_PRESET_OPEN_60_DECK, CALC_PRESET_OPEN_60_DRAWN)
        open40 = _make_preset_btn("Open 40", CALC_PRESET_OPEN_40_DECK, CALC_PRESET_OPEN_40_DRAWN)
        calc_sizer.Add(
            _centered_row(open60, open40, CALC_PRESET_BUTTON_SPACING),
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            CALC_SECTION_PADDING,
        )

        # Row 2: T3 Play | T3 Draw
        t3play = _make_preset_btn("T3 Play", CALC_PRESET_T3_PLAY_DECK, CALC_PRESET_T3_PLAY_DRAWN)
        t3draw = _make_preset_btn("T3 Draw", CALC_PRESET_T3_DRAW_DECK, CALC_PRESET_T3_DRAW_DRAWN)
        calc_sizer.Add(
            _centered_row(t3play, t3draw, CALC_PRESET_BUTTON_SPACING),
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            CALC_SECTION_PADDING,
        )

        # Row 3: Calculate | Clear
        calc_btn = wx.Button(self.calc_panel, label="Calculate", size=btn_size)
        calc_btn.SetBackgroundColour(CALC_BUTTON_GREEN)
        calc_btn.SetForegroundColour(LIGHT_TEXT)
        font = calc_btn.GetFont()
        font.MakeBold()
        calc_btn.SetFont(font)
        calc_btn.Bind(wx.EVT_BUTTON, self._on_calculate)

        clear_btn = wx.Button(self.calc_panel, label="Clear", size=btn_size)
        clear_btn.SetBackgroundColour(DARK_BG)
        clear_btn.SetForegroundColour(LIGHT_TEXT)
        clear_btn.Bind(wx.EVT_BUTTON, self._on_clear_calculator)

        calc_sizer.Add(
            _centered_row(calc_btn, clear_btn, CALC_ACTION_BUTTON_SPACING),
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            CALC_SECTION_PADDING,
        )

        # Bind Enter key on spin controls
        for spin in [
            self.spin_deck_size,
            self.spin_copies,
            self.spin_drawn,
            self.spin_target,
        ]:
            spin.Bind(wx.EVT_TEXT_ENTER, self._on_calculate)

        # Result display
        self.calc_result_label = wx.StaticText(self.calc_panel, label="")
        self.calc_result_label.SetForegroundColour(LIGHT_TEXT)
        calc_sizer.Add(self.calc_result_label, 0, wx.ALL, CALC_SECTION_PADDING)

    def _fit_left_splitter(self) -> None:
        calc_best = self.calc_panel.GetBestSize()
        sash_h = calc_best.GetHeight()
        splitter_w = calc_best.GetWidth()
        self._left_splitter.SetMinSize(wx.Size(splitter_w, -1))
        self._left_splitter.SetSashPosition(sash_h)
        self.Layout()


class _LoadArchetypeDialog(wx.Dialog):
    """Small dialog for manually selecting a format + archetype name."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        format_label: str,
        archetype_label: str,
        metagame_repository: MetagameRepository,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)
        self.SetBackgroundColour(DARK_BG)
        self._metagame_repo = metagame_repository
        self._archetypes_by_format: dict[str, list[dict[str, Any]]] = {}

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        grid = wx.FlexGridSizer(2, 2, 6, 8)
        grid.AddGrowableCol(1, 1)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        lbl_fmt = wx.StaticText(self, label=format_label)
        lbl_fmt.SetForegroundColour(LIGHT_TEXT)
        self._format_choice = wx.Choice(self, choices=FORMAT_OPTIONS)
        self._format_choice.SetSelection(0)
        self._format_choice.Bind(wx.EVT_CHOICE, self._on_format_changed)

        lbl_arch = wx.StaticText(self, label=archetype_label)
        lbl_arch.SetForegroundColour(LIGHT_TEXT)
        self._archetype_choice = wx.Choice(self, choices=[], size=(260, -1))

        grid.Add(lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._format_choice, 1, wx.EXPAND)
        grid.Add(lbl_arch, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._archetype_choice, 1, wx.EXPAND)

        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self._populate_archetype_choices()
        self.Fit()
        self.CentreOnParent()

    def get_values(self) -> tuple[str, str]:
        fmt = self._format_choice.GetString(self._format_choice.GetSelection())
        archetype = self._archetype_choice.GetStringSelection().strip()
        return fmt, archetype

    def _on_format_changed(self, _event: wx.CommandEvent) -> None:
        self._populate_archetype_choices()

    def _populate_archetype_choices(self) -> None:
        fmt = self._format_choice.GetStringSelection()
        archetypes = self._archetypes_by_format.get(fmt)
        if archetypes is None:
            try:
                archetypes = self._metagame_repo.get_archetypes_for_format(fmt)
            except Exception as exc:
                logger.warning(f"Failed to load archetype choices for {fmt}: {exc}")
                archetypes = []
            self._archetypes_by_format[fmt] = archetypes

        names = sorted(
            {
                str(archetype.get("name", "")).strip()
                for archetype in archetypes
                if str(archetype.get("name", "")).strip()
            },
            key=str.casefold,
        )
        self._archetype_choice.Set(names)
        if names:
            self._archetype_choice.SetSelection(0)


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
