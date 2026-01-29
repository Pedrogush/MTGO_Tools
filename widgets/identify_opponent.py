"""wxPython variant of the MTGO opponent tracker overlay."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import bs4
import wx
from curl_cffi import requests
from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import (
    CONFIG_DIR,
    DARK_BG,
    DARK_PANEL,
    DECK_MONITOR_CACHE_FILE,
    DECK_MONITOR_CONFIG_FILE,
    FORMAT_OPTIONS,
    GOLDFISH,
    LIGHT_TEXT,
    MTGGOLDFISH_REQUEST_TIMEOUT_SECONDS,
    OPPONENT_TRACKER_CACHE_TTL_SECONDS,
    OPPONENT_TRACKER_FRAME_SIZE,
    OPPONENT_TRACKER_LABEL_WRAP_WIDTH,
    OPPONENT_TRACKER_POLL_INTERVAL_MS,
    OPPONENT_TRACKER_SECTION_PADDING,
    OPPONENT_TRACKER_SPACER_HEIGHT,
    SUBDUED_TEXT,
)
from utils.find_opponent_names import find_opponent_names
from utils.math_utils import hypergeometric_at_least, hypergeometric_probability

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
        if len(tds) != 8:
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

    def __init__(self, parent: wx.Window | None = None) -> None:
        style = (
            wx.CAPTION | wx.CLOSE_BOX | wx.STAY_ON_TOP | wx.FRAME_FLOAT_ON_PARENT | wx.MINIMIZE_BOX
        )
        super().__init__(
            parent, title="MTGO Opponent Tracker", size=OPPONENT_TRACKER_FRAME_SIZE, style=style
        )

        self._poll_timer = wx.Timer(self)

        self.cache: dict[str, dict[str, Any]] = {}
        self.player_name: str = ""
        self.last_seen_decks: dict[str, str] = {}  # format -> deck name

        self._saved_position: list[int] | None = None
        self._calculator_visible: bool = False

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
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        self.deck_label = wx.StaticText(panel, label="Opponent not detected")
        self._stylize_label(self.deck_label)
        self.deck_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        sizer.Add(self.deck_label, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        self.status_label = wx.StaticText(panel, label="Watching for MTGO match windows…")
        self._stylize_label(self.status_label, subtle=True)
        self.status_label.Wrap(320)
        sizer.Add(
            self.status_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            OPPONENT_TRACKER_SECTION_PADDING,
        )

        divider = wx.StaticLine(panel)
        sizer.Add(
            divider, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING
        )

        controls = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(controls, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        controls.AddStretchSpacer(1)

        refresh_button = wx.Button(panel, label="Refresh")
        self._stylize_secondary_button(refresh_button)
        refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self._manual_refresh(force=True))
        controls.Add(refresh_button, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        self.calc_toggle_btn = wx.Button(panel, label="Calculator")
        self._stylize_secondary_button(self.calc_toggle_btn)
        self.calc_toggle_btn.Bind(wx.EVT_BUTTON, self._toggle_calculator_panel)
        controls.Add(self.calc_toggle_btn, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        close_button = wx.Button(panel, label="Close")
        self._stylize_secondary_button(close_button)
        close_button.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        controls.Add(close_button, 0)

        # Calculator Panel (initially hidden)
        self._build_calculator_panel(panel, sizer)

        sizer.AddSpacer(OPPONENT_TRACKER_SPACER_HEIGHT)

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

    def _build_calculator_panel(self, panel: wx.Panel, parent_sizer: wx.BoxSizer) -> None:
        """Build the collapsible hypergeometric calculator panel."""
        self.calc_panel = wx.Panel(panel)
        self.calc_panel.SetBackgroundColour(DARK_PANEL)

        calc_sizer = wx.BoxSizer(wx.VERTICAL)
        self.calc_panel.SetSizer(calc_sizer)

        # Title
        title = wx.StaticText(self.calc_panel, label="Hypergeometric Calculator")
        title.SetForegroundColour(LIGHT_TEXT)
        title_font = title.GetFont()
        title_font.MakeBold()
        title.SetFont(title_font)
        calc_sizer.Add(title, 0, wx.ALL, 6)

        # Input grid
        grid = wx.FlexGridSizer(4, 2, 4, 8)
        calc_sizer.Add(grid, 0, wx.ALL | wx.EXPAND, 6)

        # Deck Size
        lbl_deck = wx.StaticText(self.calc_panel, label="Deck Size:")
        lbl_deck.SetForegroundColour(LIGHT_TEXT)
        self.spin_deck_size = wx.SpinCtrl(
            self.calc_panel, min=1, max=250, initial=60, size=(70, -1)
        )
        self.spin_deck_size.SetToolTip("Total cards in deck (N)")
        grid.Add(lbl_deck, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_deck_size, 0)

        # Copies in Deck
        lbl_copies = wx.StaticText(self.calc_panel, label="Copies in Deck:")
        lbl_copies.SetForegroundColour(LIGHT_TEXT)
        self.spin_copies = wx.SpinCtrl(self.calc_panel, min=0, max=60, initial=4, size=(70, -1))
        self.spin_copies.SetToolTip("Number of target cards in deck (K)")
        grid.Add(lbl_copies, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_copies, 0)

        # Cards Drawn
        lbl_drawn = wx.StaticText(self.calc_panel, label="Cards Drawn:")
        lbl_drawn.SetForegroundColour(LIGHT_TEXT)
        self.spin_drawn = wx.SpinCtrl(self.calc_panel, min=0, max=60, initial=7, size=(70, -1))
        self.spin_drawn.SetToolTip("Number of cards drawn (n)")
        grid.Add(lbl_drawn, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_drawn, 0)

        # Target Copies
        lbl_target = wx.StaticText(self.calc_panel, label="Target Copies:")
        lbl_target.SetForegroundColour(LIGHT_TEXT)
        self.spin_target = wx.SpinCtrl(self.calc_panel, min=0, max=60, initial=1, size=(70, -1))
        self.spin_target.SetToolTip("Desired number of target cards (k)")
        grid.Add(lbl_target, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_target, 0)

        # Preset buttons
        preset_sizer = wx.BoxSizer(wx.HORIZONTAL)
        calc_sizer.Add(preset_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        presets = [
            ("Open 60", 60, 7),
            ("Open 40", 40, 7),
            ("T3 Play", 60, 9),
            ("T3 Draw", 60, 10),
        ]
        for label, deck, drawn in presets:
            btn = wx.Button(self.calc_panel, label=label, size=(55, 24))
            btn.SetBackgroundColour(DARK_BG)
            btn.SetForegroundColour(LIGHT_TEXT)
            btn.Bind(
                wx.EVT_BUTTON,
                lambda evt, d=deck, n=drawn: self._apply_preset(d, n),
            )
            preset_sizer.Add(btn, 0, wx.RIGHT, 4)

        # Action buttons
        action_sizer = wx.BoxSizer(wx.HORIZONTAL)
        calc_sizer.Add(action_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)

        calc_btn = wx.Button(self.calc_panel, label="Calculate")
        calc_btn.SetBackgroundColour("#2a6b2a")
        calc_btn.SetForegroundColour(LIGHT_TEXT)
        font = calc_btn.GetFont()
        font.MakeBold()
        calc_btn.SetFont(font)
        calc_btn.Bind(wx.EVT_BUTTON, self._on_calculate)
        action_sizer.Add(calc_btn, 0, wx.RIGHT, 8)

        clear_btn = wx.Button(self.calc_panel, label="Clear")
        clear_btn.SetBackgroundColour(DARK_BG)
        clear_btn.SetForegroundColour(LIGHT_TEXT)
        clear_btn.Bind(wx.EVT_BUTTON, self._on_clear_calculator)
        action_sizer.Add(clear_btn, 0)

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
        calc_sizer.Add(self.calc_result_label, 0, wx.ALL, 6)

        # Add panel to parent sizer but hide initially
        parent_sizer.Add(
            self.calc_panel,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            OPPONENT_TRACKER_SECTION_PADDING,
        )
        self.calc_panel.Hide()

    def _toggle_calculator_panel(self, _event: wx.CommandEvent | None = None) -> None:
        """Toggle calculator panel visibility."""
        self._calculator_visible = not self._calculator_visible
        if self._calculator_visible:
            self.calc_panel.Show()
            self.calc_toggle_btn.SetLabel("Hide Calc")
        else:
            self.calc_panel.Hide()
            self.calc_toggle_btn.SetLabel("Calculator")
        self.Layout()
        self.Fit()

    def _apply_preset(self, deck_size: int, cards_drawn: int) -> None:
        """Apply a preset to the calculator inputs and run calculation."""
        self.spin_deck_size.SetValue(deck_size)
        self.spin_drawn.SetValue(cards_drawn)
        self._on_calculate(None)

    def _on_calculate(self, _event: wx.CommandEvent | None) -> None:
        """Calculate and display hypergeometric probability."""
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
        """Reset calculator to default values."""
        self.spin_deck_size.SetValue(60)
        self.spin_copies.SetValue(4)
        self.spin_drawn.SetValue(7)
        self.spin_target.SetValue(1)
        self.calc_result_label.SetLabel("")

    # ------------------------------------------------------------------ Event handlers -------------------------------------------------------
    def _manual_refresh(self, force: bool = False) -> None:
        if self.player_name:
            self.cache.pop(self.player_name, None)
            self._check_for_opponent()

    # ------------------------------------------------------------------ Opponent detection ---------------------------------------------------
    def _start_polling(self) -> None:
        self.status_label.SetLabel("Watching for MTGO match windows…")
        self._poll_timer.Start(self.POLL_INTERVAL_MS)
        self._check_for_opponent()

    def _on_poll_tick(self, _event: wx.TimerEvent) -> None:
        self._check_for_opponent()

    def _check_for_opponent(self) -> None:
        try:
            opponents = find_opponent_names()
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"Failed to detect opponent from window titles: {exc}")
            self.status_label.SetLabel("Waiting for MTGO match window…")
            self.player_name = ""
            self.last_seen_decks = {}
            self._refresh_opponent_display()
            return

        if not opponents:
            self.status_label.SetLabel("No active match detected")
            self.player_name = ""
            self.last_seen_decks = {}
            self._refresh_opponent_display()
            return

        # Take the first opponent found
        opponent_name = opponents[0]

        # Only lookup decks if opponent changed
        if opponent_name != self.player_name:
            self.player_name = opponent_name
            self.last_seen_decks = self._lookup_decks_all_formats(self.player_name, force=False)

        self.status_label.SetLabel(f"Match detected: vs {self.player_name}")
        self.status_label.Wrap(320)
        self._refresh_opponent_display()

    def _lookup_decks_all_formats(
        self, opponent_name: str, *, force: bool = False
    ) -> dict[str, str]:
        """Lookup opponent's recent decks across all formats."""
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
            text = "Opponent not detected"
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
        wx.CallLater(200, self._save_config)

    def _save_config(self) -> None:
        try:
            position = list(self.GetPosition())
        except RuntimeError:
            return

        config = {
            "screen_pos": position,
            "calculator_visible": self._calculator_visible,
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
        self._calculator_visible = data.get("calculator_visible", False)

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

    def _apply_window_preferences(self) -> None:
        self.SetBackgroundColour(DARK_BG)
        if getattr(self, "_saved_position", None):
            try:
                x, y = self._saved_position
                self.SetPosition(wx.Point(int(x), int(y)))
            except (TypeError, ValueError, RuntimeError):
                logger.debug("Ignoring invalid saved window position")
        # Restore calculator panel visibility
        if getattr(self, "_calculator_visible", False):
            self.calc_panel.Show()
            self.calc_toggle_btn.SetLabel("Hide Calc")
            self.Layout()
            self.Fit()

    def _is_widget_ok(self, widget: wx.Window) -> bool:
        """Check if a widget is still valid and not destroyed."""
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
        if self._poll_timer.IsRunning():
            self._poll_timer.Stop()
        event.Skip()


__all__ = ["MTGOpponentDeckSpy"]
