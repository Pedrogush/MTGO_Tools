"""Opponent-detection polling for the tracker (``wx.Timer`` + ``BackgroundWorker``).

Periodically scans MTGO window titles for the current opponent, looks up their
recent decks across formats off the UI thread, and updates the tracker display.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants import (
    FORMAT_OPTIONS,
    OPPONENT_TRACKER_LABEL_WRAP_WIDTH,
)
from utils.find_opponent_names import find_opponent_names
from widgets.frames.identify_opponent.properties import get_latest_deck

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class OpponentPollingMixin(_Base):
    """Timer-driven opponent detection and deck lookup."""

    def _manual_refresh(self, force: bool = False) -> None:
        if not self._watching_enabled:
            return
        if self.player_name:
            self.cache.pop(self.player_name, None)
        # Cancel any in-progress poll and submit a fresh one
        self._poll_in_progress = False
        self._submit_poll()

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
