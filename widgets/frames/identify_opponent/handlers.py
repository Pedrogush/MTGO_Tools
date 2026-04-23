"""Event handlers, background workers, persistence, and window-placement logic
for the opponent tracker.

All ``_on_*`` callbacks, the polling/radar worker threads, cache/config
read-write helpers, and lifecycle hooks live here.  The legacy-path constants
and ``get_latest_deck`` helper are imported from :mod:`.properties`.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import wx
from loguru import logger

from repositories.metagame_repository import MetagameRepository
from services.radar_service import RadarData, RadarService
from utils.archetype_resolver import find_archetype_by_name
from utils.atomic_io import atomic_write_json, locked_path
from utils.background_worker import BackgroundWorker
from utils.constants import (
    ACTIVE_GUIDE_FILE,
    APP_FRAME_SIZE,
    CALC_COPIES_DEFAULT,
    CALC_DECK_SIZE_DEFAULT,
    CALC_DRAWN_DEFAULT,
    CALC_TARGET_DEFAULT,
    DARK_BG,
    DECK_MONITOR_CACHE_FILE,
    DECK_MONITOR_CONFIG_FILE,
    FORMAT_OPTIONS,
    GUIDE_STORE,
    OPPONENT_TRACKER_CONFIG_SAVE_DELAY_MS,
    OPPONENT_TRACKER_DEFAULT_X_GAP,
    OPPONENT_TRACKER_FRAME_SIZE,
    OPPONENT_TRACKER_LABEL_WRAP_WIDTH,
    OPPONENT_TRACKER_MIN_SIZE,
    OPPONENT_TRACKER_RADAR_THREAD_JOIN_TIMEOUT_SECONDS,
    RADAR_MAX_DECKS_OPPONENT_TRACKER,
)
from utils.find_opponent_names import find_opponent_names
from utils.math_utils import hypergeometric_at_least, hypergeometric_probability
from widgets.frames import identify_opponent as _pkg
from widgets.frames.identify_opponent.properties import get_latest_deck
from widgets.panels.compact_radar_panel import CompactRadarPanel
from widgets.panels.compact_sideboard_panel import CompactSideboardPanel


class MTGOpponentDeckSpyHandlersMixin:
    """Callbacks, workers, persistence, and window-placement for the tracker frame."""

    # --- typed attribute declarations for type-checker clarity ---
    CACHE_TTL: int
    POLL_INTERVAL_MS: int

    cache: dict[str, dict[str, Any]]
    player_name: str
    last_seen_decks: dict[str, str]

    _poll_timer: wx.Timer
    _saved_position: list[int] | None
    _bg_worker: BackgroundWorker
    _poll_generation: int
    _poll_in_progress: bool
    _watching_enabled: bool
    _manual_archetype_loaded: bool

    radar_service: RadarService
    metagame_repo: MetagameRepository
    current_radar: RadarData | None
    _radar_worker_thread: threading.Thread | None
    _radar_cancel_requested: bool
    _last_radar_archetype: str
    _last_guide_archetype: str

    deck_label: wx.StaticText
    status_label: wx.StaticText
    load_arch_btn: wx.Button
    calc_result_label: wx.StaticText
    spin_deck_size: wx.SpinCtrl
    spin_copies: wx.SpinCtrl
    spin_drawn: wx.SpinCtrl
    spin_target: wx.SpinCtrl
    radar_panel: CompactRadarPanel
    sideboard_panel: CompactSideboardPanel

    def _on_load_archetype_clicked(self, _event: wx.CommandEvent) -> None:
        """Open dialog to manually load an archetype for radar/guide lookup."""
        # Local import to avoid a circular dependency between frame.py and handlers.py.
        from widgets.frames.identify_opponent.frame import _LoadArchetypeDialog

        if self._manual_archetype_loaded:
            self._unload_manual_archetype()
            return

        dlg = _LoadArchetypeDialog(
            self,
            title=self._t("tracker.dlg.load_archetype.title"),
            format_label=self._t("tracker.dlg.load_archetype.format"),
            archetype_label=self._t("tracker.dlg.load_archetype.archetype"),
            metagame_repository=self.metagame_repo,
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
        self._stop_watching()
        self._clear_radar_display()
        self._manual_archetype_loaded = True
        self.player_name = "(manual)"
        self.last_seen_decks = {fmt: archetype}
        self.deck_label.SetLabel(
            self._t("tracker.label.manual_archetype", archetype=archetype, fmt=fmt)
        )
        self.deck_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        self.status_label.SetLabel(self._t("tracker.status.manual_loaded"))
        self.status_label.Wrap(OPPONENT_TRACKER_LABEL_WRAP_WIDTH)
        self.load_arch_btn.SetLabel(self._t("tracker.btn.unload_archetype"))
        self._trigger_radar_load()
        self._update_guide_display()

    def _unload_manual_archetype(self) -> None:
        self._manual_archetype_loaded = False
        self.player_name = ""
        self.last_seen_decks = {}
        self.load_arch_btn.SetLabel(self._t("tracker.btn.load_archetype"))
        self._clear_radar_display()
        self._refresh_opponent_display()
        self._start_polling()

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
        if not self._watching_enabled:
            return
        if self.player_name:
            self.cache.pop(self.player_name, None)
        # Cancel any in-progress poll and submit a fresh one
        self._poll_in_progress = False
        self._submit_poll()

    # ------------------------------------------------------------------ Opponent detection ---------------------------------------------------
    def _start_polling(self) -> None:
        self._watching_enabled = True
        self.status_label.SetLabel(self._t("tracker.label.watching"))
        if not self._poll_timer.IsRunning():
            self._poll_timer.Start(self.POLL_INTERVAL_MS)
        self._submit_poll()

    def _stop_watching(self) -> None:
        self._watching_enabled = False
        self._poll_generation += 1
        self._poll_in_progress = False
        if self._poll_timer.IsRunning():
            self._poll_timer.Stop()

    def _on_poll_tick(self, _event: wx.TimerEvent) -> None:
        self._submit_poll()

    def _submit_poll(self) -> None:
        if not self._watching_enabled:
            return
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
        if not self._watching_enabled:
            return

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
        if not source_file.exists() and _pkg.LEGACY_DECK_MONITOR_CONFIG.exists():
            source_file = _pkg.LEGACY_DECK_MONITOR_CONFIG
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
            _pkg.LEGACY_DECK_MONITOR_CACHE_CONFIG,
            _pkg.LEGACY_DECK_MONITOR_CACHE,
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

        # Match the main app's height so the tracker feels aligned when placed side by side.
        try:
            display_idx = wx.Display.GetFromWindow(self) if self.IsShown() else 0
            if display_idx == wx.NOT_FOUND:
                display_idx = 0
            client_area = wx.Display(display_idx).GetClientArea()
            frame_w, _ = OPPONENT_TRACKER_FRAME_SIZE
            parent = self.GetParent()
            main_h = parent.GetSize().GetHeight() if parent is not None else APP_FRAME_SIZE[1]
            self.SetSize(frame_w, min(main_h, client_area.GetHeight()))
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
