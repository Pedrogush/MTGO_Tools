"""Config/cache JSON persistence (with legacy migration) for the opponent tracker.

Reads and writes the window-position config and the opponent-deck cache, and
migrates the pre-``config/`` legacy files on first load.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import (
    DECK_MONITOR_CACHE_FILE,
    DECK_MONITOR_CONFIG_FILE,
    OPPONENT_TRACKER_CONFIG_SAVE_DELAY_MS,
)
from widgets.frames import identify_opponent as _pkg

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class PersistenceMixin(_Base):
    """Config/cache read-write helpers and legacy migration."""

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
