"""Radar worker-thread orchestration for the opponent tracker.

Resolves the opponent's archetype, runs :class:`RadarService` on a daemon
thread, and marshals progress/results/errors back onto the wx UI thread.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from utils.constants import RADAR_MAX_DECKS_OPPONENT_TRACKER

if TYPE_CHECKING:
    from services.radar_service import RadarData
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class RadarMixin(_Base):
    """Background radar generation for the detected opponent's archetype."""

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
        archetype_dict = self.controller.find_archetype_by_name(
            archetype_name, format_name, self.metagame_service.metagame_repo
        )

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
