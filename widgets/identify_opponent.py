"""wxPython variant of the MTGO opponent tracker overlay."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the project root is on sys.path when the file is run directly
# (e.g. `python widgets/identify_opponent.py`).  Has no effect when the
# package is imported normally or via the installed console script.
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import json
import threading
import time
from pathlib import Path
from typing import Any

import bs4
import wx
from curl_cffi import requests
from loguru import logger

from repositories.metagame_repository import MetagameRepository, get_metagame_repository
from services.radar_service import RadarData, RadarService, get_radar_service
from utils.archetype_resolver import find_archetype_by_name
from utils.atomic_io import atomic_write_json, locked_path
from utils.background_worker import BackgroundWorker
from utils.constants import (
    ACTIVE_GUIDE_FILE,
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
    CONFIG_DIR,
    DARK_BG,
    DARK_PANEL,
    DECK_MONITOR_CACHE_FILE,
    DECK_MONITOR_CONFIG_FILE,
    FORMAT_OPTIONS,
    GOLDFISH,
    GOLDFISH_PLAYER_TABLE_COLUMNS,
    GUIDE_STORE,
    LIGHT_TEXT,
    MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
    OPPONENT_TRACKER_CACHE_TTL_SECONDS,
    OPPONENT_TRACKER_CONFIG_SAVE_DELAY_MS,
    OPPONENT_TRACKER_DEFAULT_X_GAP,
    OPPONENT_TRACKER_FRAME_SIZE,
    OPPONENT_TRACKER_LABEL_WRAP_WIDTH,
    OPPONENT_TRACKER_LEFT_SASH_POS,
    OPPONENT_TRACKER_RADAR_PANEL_HEIGHT,
    OPPONENT_TRACKER_MIN_SIZE,
    OPPONENT_TRACKER_POLL_INTERVAL_MS,
    OPPONENT_TRACKER_RADAR_THREAD_JOIN_TIMEOUT_SECONDS,
    OPPONENT_TRACKER_SECTION_PADDING,
    RADAR_MAX_DECKS_OPPONENT_TRACKER,
    SUBDUED_TEXT,
)
from utils.find_opponent_names import find_opponent_names
from utils.i18n import translate
from utils.math_utils import hypergeometric_at_least, hypergeometric_probability
from widgets.panels.compact_radar_panel import CompactRadarPanel
from widgets.panels.compact_sideboard_panel import CompactSideboardPanel

LEGACY_DECK_MONITOR_CONFIG = Path("deck_monitor_config.json")
LEGACY_DECK_MONITOR_CACHE = Path("deck_monitor_cache.json")
LEGACY_DECK_MONITOR_CACHE_CONFIG = CONFIG_DIR / "deck_monitor_cache.json"


def get_latest_deck(player: str, option: str):
    """
    Web scraping function: queries MTGGoldfish for a player's recent tournament results.
    Returns the most recent deck archetype the player used in the specified format.
    This is read-only web scraping and does not interact with MTGO client.
    """
    if not player:
        return "No player name"
    logger.debug(player)
    player = player.strip()
    try:
        res = requests.get(
            GOLDFISH + player,
            impersonate="chrome",
            timeout=MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
        )
        res.raise_for_status()
    except Exception as exc:
        logger.error(f"Failed to fetch player page for {player}: {exc}")
        return "Unknown"
    soup = bs4.BeautifulSoup(res.text, "lxml")
    table = soup.find("table")
    if not table and player[0] == "0":
        logger.debug("ocr possibly mistook the letter O for a zero")
        player = "O" + player[1:]
        logger.debug(player)
        try:
            res = requests.get(
                GOLDFISH + player,
                impersonate="chrome",
                timeout=MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
            )
            res.raise_for_status()
        except Exception as exc:
            logger.error(f"Failed retry fetch for player {player}: {exc}")
            return "Unknown"
        soup = bs4.BeautifulSoup(res.text, "lxml")
        table = soup.find("table")
    if not table:
        logger.debug(f"No results table found for player {player}")
        return "Unknown"
    entries = table.find_all("tr")
    for entry in entries:
        tds = entry.find_all("td")
        if not tds:
            continue
        if len(tds) != GOLDFISH_PLAYER_TABLE_COLUMNS:
            continue
        entry_format: str = tds[2].text
        if entry_format.lower().strip() == option.lower():
            logger.debug(f"{player} last 5-0 seen playing {tds[3].text}, in {tds[0].text}")
            return tds[3].text

    return "Unknown"


class MTGOpponentDeckSpy(wx.Frame):
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

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

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

        load_arch_btn = wx.Button(panel, label=self._t("tracker.btn.load_archetype"))
        self._stylize_secondary_button(load_arch_btn)
        load_arch_btn.Bind(wx.EVT_BUTTON, self._on_load_archetype_clicked)
        controls.Add(load_arch_btn, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

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
            self._left_splitter, 0, wx.RIGHT | wx.ALIGN_TOP, OPPONENT_TRACKER_SECTION_PADDING
        )

        self._build_calculator_panel(self._left_splitter)

        self.radar_panel = CompactRadarPanel(self._left_splitter)
        self.radar_panel.clear()  # show placeholder (does not hide in new layout)

        self._left_splitter.SplitHorizontally(
            self.calc_panel, self.radar_panel, OPPONENT_TRACKER_LEFT_SASH_POS
        )
        self._left_splitter.SetMinimumPaneSize(80)
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
        total_h = sash_h + OPPONENT_TRACKER_RADAR_PANEL_HEIGHT
        self._left_splitter.SetSize(wx.Size(splitter_w, total_h))
        self._left_splitter.SetSashPosition(sash_h)
        self.Layout()

    def _on_load_archetype_clicked(self, _event: wx.CommandEvent) -> None:
        """Open dialog to manually load an archetype for radar/guide lookup."""
        dlg = _LoadArchetypeDialog(
            self,
            title=self._t("tracker.dlg.load_archetype.title"),
            format_label=self._t("tracker.dlg.load_archetype.format"),
            archetype_label=self._t("tracker.dlg.load_archetype.archetype"),
            locale=self._locale,
        )
        if dlg.ShowModal() == wx.ID_OK:
            fmt, archetype = dlg.get_values()
            if fmt and archetype:
                self._load_archetype_manually(fmt, archetype)
        dlg.Destroy()

    def _update_guide_display(self) -> None:
        if not self.last_seen_decks:
            self.sideboard_panel.clear()
            return

        _format_name, archetype_name = next(iter(self.last_seen_decks.items()))
        if not archetype_name or archetype_name == "Unknown":
            self.sideboard_panel.clear()
            return

        # Load pinned guide
        if not ACTIVE_GUIDE_FILE.exists():
            self.sideboard_panel.set_no_pinned_deck()
            return

        try:
            with ACTIVE_GUIDE_FILE.open("r", encoding="utf-8") as fh:
                active = json.load(fh)
        except Exception as exc:
            logger.warning(f"Failed to read active guide file: {exc}")
            self.sideboard_panel.set_no_pinned_deck()
            return

        deck_hash = active.get("deck_hash", "")
        if not deck_hash:
            self.sideboard_panel.set_no_pinned_deck()
            return

        # Load guide store
        try:
            if GUIDE_STORE.exists():
                with GUIDE_STORE.open("r", encoding="utf-8") as fh:
                    guide_store = json.load(fh)
            else:
                guide_store = {}
        except Exception as exc:
            logger.warning(f"Failed to read guide store: {exc}")
            guide_store = {}

        payload = guide_store.get(deck_hash) or {}
        entries: list[dict] = payload.get("entries", [])
        exclusions: list[str] = payload.get("exclusions", [])

        if not entries:
            self.sideboard_panel.set_no_guide(archetype_name)
            return

        # Find matching entry (case-insensitive substring match)
        archetype_lower = archetype_name.lower()
        match = None
        for entry in entries:
            entry_arch = entry.get("archetype", "")
            if entry_arch in exclusions:
                continue
            if entry_arch.lower() == archetype_lower:
                match = entry
                break
        if match is None:
            for entry in entries:
                entry_arch = entry.get("archetype", "")
                if entry_arch in exclusions:
                    continue
                if archetype_lower in entry_arch.lower() or entry_arch.lower() in archetype_lower:
                    match = entry
                    break

        if match is None:
            self.sideboard_panel.set_no_guide(archetype_name)
        else:
            self.sideboard_panel.display_entry(match, archetype_name)

    def _load_archetype_manually(self, fmt: str, archetype: str) -> None:
        """Load radar and guide for a manually specified archetype."""
        self._clear_radar_display()
        self.player_name = "(manual)"
        self.last_seen_decks = {fmt: archetype}
        self.deck_label.SetLabel(
            self._t("tracker.label.manual_archetype", archetype=archetype, fmt=fmt)
        )
        self.deck_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        self._trigger_radar_load()
        self._update_guide_display()

    def _apply_preset(self, deck_size: int, cards_drawn: int) -> None:
        self.spin_deck_size.SetValue(deck_size)
        self.spin_drawn.SetValue(cards_drawn)
        self._on_calculate(None)

    def _on_calculate(self, _event: wx.CommandEvent | None) -> None:
        try:
            deck_size = self.spin_deck_size.GetValue()
            copies = self.spin_copies.GetValue()
            drawn = self.spin_drawn.GetValue()
            target = self.spin_target.GetValue()

            # Validate inputs
            if copies > deck_size:
                self.calc_result_label.SetLabel("Error: Copies > Deck Size")
                return
            if drawn > deck_size:
                self.calc_result_label.SetLabel("Error: Drawn > Deck Size")
                return
            if target > copies:
                self.calc_result_label.SetLabel("Error: Target > Copies")
                return
            if target > drawn:
                self.calc_result_label.SetLabel("Error: Target > Drawn")
                return

            exact_prob = hypergeometric_probability(deck_size, copies, drawn, target)
            at_least_prob = hypergeometric_at_least(deck_size, copies, drawn, target)

            result_text = (
                f"Exact ({target}): {exact_prob * 100:.2f}%\n"
                f"At least {target}: {at_least_prob * 100:.2f}%"
            )
            self.calc_result_label.SetLabel(result_text)

        except ValueError as e:
            self.calc_result_label.SetLabel(f"Error: {e}")
        except Exception as e:
            logger.error(f"Calculator error: {e}")
            self.calc_result_label.SetLabel("Calculation error")

    def _on_clear_calculator(self, _event: wx.CommandEvent) -> None:
        self.spin_deck_size.SetValue(CALC_DECK_SIZE_DEFAULT)
        self.spin_copies.SetValue(CALC_COPIES_DEFAULT)
        self.spin_drawn.SetValue(CALC_DRAWN_DEFAULT)
        self.spin_target.SetValue(CALC_TARGET_DEFAULT)
        self.calc_result_label.SetLabel("")

    # ------------------------------------------------------------------ Radar integration ---------------------------------------------------
    def _trigger_radar_load(self) -> None:
        """
        Trigger radar loading for the opponent's archetype.

        Called after opponent deck is successfully looked up.
        Picks the first format with a known deck and loads radar for that archetype.
        """
        if not self.last_seen_decks:
            return

        # Pick first format with a known deck
        format_name, archetype_name = next(iter(self.last_seen_decks.items()))

        if not archetype_name or archetype_name == "Unknown":
            logger.debug("Skipping radar load: no valid archetype")
            return

        # Skip if same archetype already loaded or currently loading
        if archetype_name == self._last_radar_archetype:
            logger.debug(f"Radar already loaded for {archetype_name}")
            return

        if self._radar_worker_thread and self._radar_worker_thread.is_alive():
            logger.debug("Radar loading already in progress")
            return

        # Resolve archetype name to archetype dict
        archetype_dict = find_archetype_by_name(archetype_name, format_name, self.metagame_repo)

        if not archetype_dict:
            logger.warning(f"Could not resolve archetype: {archetype_name} in {format_name}")
            wx.CallAfter(self.radar_panel.set_error, f"Archetype '{archetype_name}' not found")
            return

        # Update tracking
        self._last_radar_archetype = archetype_name

        # Show loading state
        wx.CallAfter(self.radar_panel.set_loading, f"Loading radar for {archetype_name}...")

        # Start background thread to generate radar
        self._radar_cancel_requested = False
        self._radar_worker_thread = threading.Thread(
            target=self._generate_radar_worker,
            args=(archetype_dict, format_name),
            daemon=True,
        )
        self._radar_worker_thread.start()
        logger.info(f"Started radar generation for {archetype_name} ({format_name})")

    def _generate_radar_worker(self, archetype_dict: dict[str, Any], format_name: str) -> None:
        try:
            # Progress callback - safely updates UI from worker thread
            def update_progress(current: int, total: int, deck_name: str) -> None:
                if self._radar_cancel_requested:
                    raise InterruptedError("Radar generation cancelled")

                # Update status label with progress
                wx.CallAfter(
                    self.radar_panel.set_loading,
                    f"Analyzing deck {current}/{total}...",
                )

            # Calculate radar (this is the I/O heavy operation)
            radar = self.radar_service.calculate_radar(
                archetype_dict,
                format_name,
                max_decks=RADAR_MAX_DECKS_OPPONENT_TRACKER,
                progress_callback=update_progress,
            )

            # Display results on UI thread
            if not self._radar_cancel_requested:
                wx.CallAfter(self._display_radar, radar)

        except InterruptedError:
            # User cancelled or switched opponents
            logger.info("Radar generation cancelled")
            wx.CallAfter(self.radar_panel.clear)

        except Exception as exc:
            # Error occurred
            logger.exception(f"Failed to generate radar: {exc}")
            wx.CallAfter(self.radar_panel.set_error, "Failed to load radar")

        finally:
            # Reset worker thread reference
            self._radar_worker_thread = None

    def _display_radar(self, radar: RadarData) -> None:
        self.current_radar = radar
        self.radar_panel.display_radar(radar)
        logger.info(f"Radar displayed for {radar.archetype_name}")

    def _clear_radar_display(self) -> None:
        self._radar_cancel_requested = True
        self.current_radar = None
        self._last_radar_archetype = ""
        self.radar_panel.clear()
        self._last_guide_archetype = ""
        self.sideboard_panel.clear()

    # ------------------------------------------------------------------ Event handlers -------------------------------------------------------
    def _manual_refresh(self, force: bool = False) -> None:
        if self.player_name:
            self.cache.pop(self.player_name, None)
        # Cancel any in-progress poll and submit a fresh one
        self._poll_in_progress = False
        self._submit_poll()

    # ------------------------------------------------------------------ Opponent detection ---------------------------------------------------
    def _start_polling(self) -> None:
        self.status_label.SetLabel(self._t("tracker.label.watching"))
        self._poll_timer.Start(self.POLL_INTERVAL_MS)
        self._submit_poll()

    def _on_poll_tick(self, _event: wx.TimerEvent) -> None:
        self._submit_poll()

    def _submit_poll(self) -> None:
        if self._poll_in_progress:
            return
        self._poll_in_progress = True
        self._poll_generation += 1
        self._bg_worker.submit(
            self._poll_worker,
            self._poll_generation,
            self.player_name,
            on_success=self._apply_poll_result,
            on_error=self._on_poll_error,
        )

    def _poll_worker(self, generation: int, current_player: str) -> dict:
        try:
            opponents = find_opponent_names()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to detect opponent from window titles: {exc}")
            return {"generation": generation, "kind": "error"}

        if not opponents:
            return {"generation": generation, "kind": "no_match"}

        opponent_name = opponents[0]
        if opponent_name == current_player:
            return {"generation": generation, "kind": "same", "opponent": opponent_name}

        decks = self._lookup_decks_all_formats(opponent_name, force=False)
        return {"generation": generation, "kind": "new", "opponent": opponent_name, "decks": decks}

    def _on_poll_error(self, exc: Exception) -> None:
        self._poll_in_progress = False
        logger.error(f"Unexpected poll worker error: {exc}")

    def _apply_poll_result(self, result: dict) -> None:
        if result["generation"] != self._poll_generation:
            return  # Stale — a newer poll supersedes this one

        self._poll_in_progress = False
        kind = result["kind"]

        if kind in ("error", "no_match"):
            label = (
                self._t("tracker.status.waiting")
                if kind == "error"
                else self._t("tracker.status.no_active_match")
            )
            self.status_label.SetLabel(label)
            self.player_name = ""
            self.last_seen_decks = {}
            self._clear_radar_display()
            self._refresh_opponent_display()
            return

        opponent_name = result["opponent"]
        if kind == "new":
            self.player_name = opponent_name
            self._clear_radar_display()
            self.last_seen_decks = result["decks"]
            if self.last_seen_decks:
                self._trigger_radar_load()
                self._update_guide_display()

        self.status_label.SetLabel(f"Match detected: vs {self.player_name}")
        self.status_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        self._refresh_opponent_display()

    def _lookup_decks_all_formats(
        self, opponent_name: str, *, force: bool = False
    ) -> dict[str, str]:
        cached = self.cache.get(opponent_name)
        now = time.time()

        # Check if we have valid cached data
        if not force and cached and now - cached.get("ts", 0) < self.CACHE_TTL:
            return cached.get("decks", {})

        # Search across all formats
        decks = {}
        for fmt in FORMAT_OPTIONS:
            try:
                deck = get_latest_deck(opponent_name, fmt)
                if deck:  # Only include if deck was found
                    decks[fmt] = deck
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"Failed to lookup {fmt} deck for {opponent_name}: {exc}")
                continue

        # Cache the results
        self.cache[opponent_name] = {"decks": decks, "ts": now}
        self._save_cache()
        return decks

    def _refresh_opponent_display(self) -> None:
        if not self.player_name:
            text = self._t("tracker.label.not_detected")
        elif not self.last_seen_decks:
            text = f"{self.player_name}: no recent decks found"
        elif len(self.last_seen_decks) == 1:
            # Single format found
            fmt, deck = next(iter(self.last_seen_decks.items()))
            text = f"{self.player_name}: {deck} ({fmt})"
        else:
            # Multiple formats found - list all
            lines = [f"{self.player_name}:"]
            for fmt, deck in sorted(self.last_seen_decks.items()):
                lines.append(f"  • {fmt}: {deck}")
            text = "\n".join(lines)

        self.deck_label.SetLabel(text)
        self.deck_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)

    # ------------------------------------------------------------------ Persistence -----------------------------------------------------------
    def _persist_config_async(self) -> None:
        wx.CallLater(OPPONENT_TRACKER_CONFIG_SAVE_DELAY_MS, self._save_config)

    def _save_config(self) -> None:
        try:
            position = list(self.GetPosition())
        except RuntimeError:
            return

        config = {
            "screen_pos": position,
        }
        try:
            atomic_write_json(DECK_MONITOR_CONFIG_FILE, config, indent=4)
        except OSError as exc:
            logger.warning(f"Failed to write deck monitor config: {exc}")

    def _load_config(self) -> None:
        source_file = DECK_MONITOR_CONFIG_FILE
        legacy_source = False
        if not source_file.exists() and LEGACY_DECK_MONITOR_CONFIG.exists():
            source_file = LEGACY_DECK_MONITOR_CONFIG
            legacy_source = True
            logger.warning("Loaded legacy deck_monitor_config.json; migrating to config/")

        if not source_file.exists():
            return

        try:
            with locked_path(source_file):
                with source_file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning(f"Invalid deck monitor config: {exc}")
            return

        if legacy_source:
            try:
                atomic_write_json(DECK_MONITOR_CONFIG_FILE, data, indent=4)
            except OSError as exc:
                logger.warning(f"Failed to migrate deck monitor config: {exc}")
        self._saved_position = data.get("screen_pos")

    def _save_cache(self) -> None:
        payload = {"entries": self.cache}
        try:
            atomic_write_json(DECK_MONITOR_CACHE_FILE, payload, indent=2)
        except OSError as exc:
            logger.debug(f"Unable to write deck monitor cache: {exc}")

    def _load_cache(self) -> None:
        candidates = [
            DECK_MONITOR_CACHE_FILE,
            LEGACY_DECK_MONITOR_CACHE_CONFIG,
            LEGACY_DECK_MONITOR_CACHE,
        ]
        for candidate in candidates:
            if not candidate.exists():
                continue
            try:
                with locked_path(candidate):
                    with candidate.open("r", encoding="utf-8") as fh:
                        data = json.load(fh)
            except json.JSONDecodeError:
                logger.debug(f"Skipping invalid cache file {candidate}")
                continue
            entries = data.get("entries") if isinstance(data, dict) else None
            if isinstance(entries, dict):
                self.cache = entries
            if candidate != DECK_MONITOR_CACHE_FILE:
                self._save_cache()
                try:
                    candidate.unlink()
                except OSError:
                    logger.debug(f"Unable to remove legacy cache {candidate}")
            break

    def _place_beside_parent(self) -> None:
        parent = self.GetParent()
        if parent is None:
            return
        try:
            pr = parent.GetRect()
            my_size = self.GetSize()
            display_idx = wx.Display.GetFromWindow(parent)
            if display_idx == wx.NOT_FOUND:
                display_idx = 0
            client_area = wx.Display(display_idx).GetClientArea()
            x = pr.GetRight() + OPPONENT_TRACKER_DEFAULT_X_GAP
            y = pr.GetTop()
            # If it doesn't fit to the right, try the left side of the parent
            if x + my_size.width > client_area.GetRight():
                x = pr.GetLeft() - my_size.width - OPPONENT_TRACKER_DEFAULT_X_GAP
            # Clamp to client area
            x = max(client_area.GetLeft(), min(x, client_area.GetRight() - my_size.width))
            y = max(client_area.GetTop(), min(y, client_area.GetBottom() - my_size.height))
            self.SetPosition(wx.Point(x, y))
        except (RuntimeError, AttributeError):
            logger.debug("Could not compute default tracker position from parent")

    def _apply_window_preferences(self) -> None:
        self.SetBackgroundColour(DARK_BG)
        self.SetMinSize(wx.Size(*OPPONENT_TRACKER_MIN_SIZE))

        # Size the window: width = ~half main app, height = full screen client area
        try:
            display_idx = wx.Display.GetFromWindow(self) if self.IsShown() else 0
            if display_idx == wx.NOT_FOUND:
                display_idx = 0
            client_area = wx.Display(display_idx).GetClientArea()
            frame_w, _ = OPPONENT_TRACKER_FRAME_SIZE
            self.SetSize(frame_w, client_area.GetHeight())
        except Exception:
            pass  # fall back to the constant size set in __init__

        if getattr(self, "_saved_position", None):
            try:
                x, y = self._saved_position
                self.SetPosition(wx.Point(int(x), int(y)))
            except (TypeError, ValueError, RuntimeError):
                logger.debug("Ignoring invalid saved window position")
                self._place_beside_parent()
        else:
            self._place_beside_parent()

    def _is_widget_ok(self, widget: wx.Window) -> bool:
        if widget is None:
            return False
        try:
            # Try to access a basic property to verify widget is still valid
            _ = widget.GetId()
            return True
        except (RuntimeError, AttributeError):
            return False

    # ------------------------------------------------------------------ Lifecycle -------------------------------------------------------------
    def on_close(self, event: wx.CloseEvent) -> None:
        self._save_config()

        # Cancel any running radar worker
        if self._radar_worker_thread and self._radar_worker_thread.is_alive():
            self._radar_cancel_requested = True
            # Give it a moment to clean up
            self._radar_worker_thread.join(
                timeout=OPPONENT_TRACKER_RADAR_THREAD_JOIN_TIMEOUT_SECONDS
            )

        if self._poll_timer.IsRunning():
            self._poll_timer.Stop()
        self._bg_worker.shutdown(timeout=5.0)
        event.Skip()


class _LoadArchetypeDialog(wx.Dialog):
    """Small dialog for manually selecting a format + archetype name."""

    def __init__(
        self,
        parent: wx.Window,
        title: str,
        format_label: str,
        archetype_label: str,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE)
        self.SetBackgroundColour(DARK_BG)

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        grid = wx.FlexGridSizer(2, 2, 6, 8)
        grid.AddGrowableCol(1, 1)
        sizer.Add(grid, 0, wx.EXPAND | wx.ALL, 12)

        lbl_fmt = wx.StaticText(self, label=format_label)
        lbl_fmt.SetForegroundColour(LIGHT_TEXT)
        self._format_choice = wx.Choice(self, choices=FORMAT_OPTIONS)
        self._format_choice.SetSelection(0)

        lbl_arch = wx.StaticText(self, label=archetype_label)
        lbl_arch.SetForegroundColour(LIGHT_TEXT)
        self._archetype_ctrl = wx.TextCtrl(self, size=(260, -1))

        grid.Add(lbl_fmt, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._format_choice, 1, wx.EXPAND)
        grid.Add(lbl_arch, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self._archetype_ctrl, 1, wx.EXPAND)

        btn_sizer = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btn_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 12)

        self.Fit()
        self.CentreOnParent()

    def get_values(self) -> tuple[str, str]:
        fmt = self._format_choice.GetString(self._format_choice.GetSelection())
        archetype = self._archetype_ctrl.GetValue().strip()
        return fmt, archetype


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


__all__ = ["MTGOpponentDeckSpy", "_LoadArchetypeDialog"]
