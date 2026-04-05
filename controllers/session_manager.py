from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger

from utils.atomic_io import atomic_write_json, locked_path
from utils.constants import FORMAT_OPTIONS
from utils.deck import sanitize_zone_cards
from utils.i18n import DEFAULT_LOCALE, SUPPORTED_LOCALES, normalize_locale


class DeckSelectorSessionManager:
    """Encapsulates deck selector settings/config persistence and restoration."""

    def __init__(
        self,
        deck_repo,
        settings_file: Path | None = None,
        config_file: Path | None = None,
        default_deck_dir: Path | None = None,
    ) -> None:
        # Lazy lookup so that monkeypatching utils.constants in tests takes effect.
        from utils.constants import (  # noqa: PLC0415
            CONFIG_FILE as _CF,
        )
        from utils.constants import (
            DECK_SELECTOR_SETTINGS_FILE as _SF,
        )
        from utils.constants import (
            DECKS_DIR as _DD,
        )

        self.deck_repo = deck_repo
        self.settings_file = settings_file if settings_file is not None else _SF
        self.config_file = config_file if config_file is not None else _CF
        self.default_deck_dir = default_deck_dir if default_deck_dir is not None else _DD

        self.settings: dict[str, Any] = self._load_json_file(self.settings_file)
        self.config: dict[str, Any] = self._load_json_file(self.config_file)

    # ------------------------------------------------------------------ helpers ------------------------------------------------------------------
    @staticmethod
    def _load_json_file(path: Path) -> dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with locked_path(path):
                with path.open("r", encoding="utf-8") as fh:
                    return json.load(fh)
        except json.JSONDecodeError as exc:
            logger.warning(f"Invalid JSON at {path}: {exc}")
            return {}

    def get_current_format(self, default: str = "Modern") -> str:
        fmt = self.settings.get("format", default)
        if fmt not in FORMAT_OPTIONS:
            return default
        return fmt

    def get_left_mode(self, default: str = "research") -> str:
        mode = self.settings.get("left_mode", default)
        return mode if mode in {"builder", "research"} else default

    def get_deck_data_source(self, default: str = "both") -> str:
        source = self.settings.get("deck_data_source", default)
        return source if source in {"mtggoldfish", "mtgo", "both"} else default

    def update_deck_data_source(self, source: str) -> None:
        valid_source = source if source in {"mtggoldfish", "mtgo", "both"} else "both"
        self.settings["deck_data_source"] = valid_source

    def get_language(self, default: str = DEFAULT_LOCALE) -> str:
        language = self.settings.get("language", default)
        return normalize_locale(language)

    def update_language(self, language: str) -> None:
        valid_language = language if language in SUPPORTED_LOCALES else DEFAULT_LOCALE
        self.settings["language"] = valid_language

    def get_average_method(self, default: str = "karsten") -> str:
        method = self.settings.get("average_method", default)
        return method if method in {"karsten", "arithmetic"} else default

    def update_average_method(self, method: str) -> None:
        valid = method if method in {"karsten", "arithmetic"} else "karsten"
        self.settings["average_method"] = valid

    _VALID_AVERAGE_HOURS = {12, 24, 36, 48, 60, 72}

    def get_average_hours(self, default: int = 24) -> int:
        value = self.settings.get("average_hours", default)
        try:
            hours = int(value)
        except (TypeError, ValueError):
            return default
        return hours if hours in self._VALID_AVERAGE_HOURS else default

    def update_average_hours(self, hours: int) -> None:
        valid = hours if hours in self._VALID_AVERAGE_HOURS else 24
        self.settings["average_hours"] = valid

    def get_event_logging_enabled(self, default: bool = False) -> bool:
        value = self.settings.get("event_logging_enabled", default)
        return bool(value)

    def update_event_logging_enabled(self, enabled: bool) -> None:
        self.settings["event_logging_enabled"] = bool(enabled)

    _VALID_EVENT_TYPE_FILTERS = {"All", "Challenge", "League", "Showcase", "Last Chance"}

    def get_deck_event_type_filter(self, default: str = "All") -> str:
        value = self.settings.get("deck_event_type_filter", default)
        return value if value in self._VALID_EVENT_TYPE_FILTERS else default

    def update_deck_event_type_filter(self, value: str) -> None:
        self.settings["deck_event_type_filter"] = (
            value if value in self._VALID_EVENT_TYPE_FILTERS else "All"
        )

    def get_deck_result_filter(self, default: str = "") -> str:
        return str(self.settings.get("deck_result_filter", default))

    def update_deck_result_filter(self, value: str) -> None:
        self.settings["deck_result_filter"] = value

    def get_deck_player_filter(self, default: str = "") -> str:
        return str(self.settings.get("deck_player_filter", default))

    def update_deck_player_filter(self, value: str) -> None:
        self.settings["deck_player_filter"] = value

    def get_deck_date_filter(self, default: str = "") -> str:
        return str(self.settings.get("deck_date_filter", default))

    def update_deck_date_filter(self, value: str) -> None:
        self.settings["deck_date_filter"] = value

    def is_tutorial_shown(self) -> bool:
        """Return True if the user has already seen the first-run tutorial."""
        return bool(self.settings.get("tutorial_shown", False))

    def mark_tutorial_shown(self) -> None:
        """Persist that the tutorial has been shown so it won't auto-open again."""
        self.settings["tutorial_shown"] = True
        try:
            atomic_write_json(self.settings_file, self.settings, indent=2)
        except OSError as exc:
            logger.warning(f"Unable to persist tutorial_shown flag: {exc}")

    def ensure_deck_save_dir(self) -> Path:
        """Resolve the deck save directory from config, creating it if needed."""
        raw_path = self.config.get("deck_selector_save_path") or self.default_deck_dir
        path = Path(raw_path).expanduser()
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(f"Unable to create deck save directory '{path}': {exc}")
            path = self.default_deck_dir
            path.mkdir(parents=True, exist_ok=True)

        if self.config.get("deck_selector_save_path") != str(path):
            self.config["deck_selector_save_path"] = str(path)
            self._persist_config()
        return path

    def _persist_config(self) -> None:
        try:
            atomic_write_json(self.config_file, self.config, indent=2)
        except OSError as exc:
            logger.warning(f"Unable to persist config at {self.config_file}: {exc}")

    # ------------------------------------------------------------------ persistence ------------------------------------------------------------------
    def save(
        self,
        *,
        current_format: str,
        left_mode: str,
        deck_data_source: str,
        zone_cards: dict[str, list[dict[str, Any]]],
        window_size: tuple[int, int] | None = None,
        screen_pos: tuple[int, int] | None = None,
    ) -> None:
        """Persist controller state and current deck data to the settings file."""
        data = dict(self.settings)
        data.update(
            {
                "format": current_format,
                "left_mode": left_mode,
                "deck_data_source": deck_data_source,
                "language": self.get_language(),
                "average_method": self.get_average_method(),
                "average_hours": self.get_average_hours(),
                "saved_deck_text": self.deck_repo.get_current_deck_text(),
                "saved_zone_cards": self._serialize_zone_cards(zone_cards),
            }
        )

        if window_size:
            data["window_size"] = list(window_size)
        if screen_pos:
            data["screen_pos"] = list(screen_pos)

        current_deck = self.deck_repo.get_current_deck()
        if current_deck:
            data["saved_deck_info"] = current_deck
        elif "saved_deck_info" in data:
            data.pop("saved_deck_info")

        try:
            atomic_write_json(self.settings_file, data, indent=2)
        except OSError as exc:
            logger.warning(f"Unable to persist deck selector settings: {exc}")
            return

        self.settings = data

    def _serialize_zone_cards(self, zone_cards: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        return {zone: sanitize_zone_cards(cards) for zone, cards in zone_cards.items()}

    # ------------------------------------------------------------------ restoration ------------------------------------------------------------------
    def restore_session_state(self, zone_cards: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        """Restore deck/session state from persisted settings."""
        result: dict[str, Any] = {"left_mode": self.get_left_mode()}

        saved_zones = self.settings.get("saved_zone_cards") or {}
        changed = False
        for zone in ("main", "side", "out"):
            entries = saved_zones.get(zone, [])
            if not isinstance(entries, list):
                continue
            sanitized = sanitize_zone_cards(entries)
            if sanitized:
                zone_cards[zone] = sanitized
                changed = True
        if changed:
            result["zone_cards"] = zone_cards

        saved_text = self.settings.get("saved_deck_text", "")
        if saved_text:
            self.deck_repo.set_current_deck_text(saved_text)
            result["deck_text"] = saved_text

        saved_deck = self.settings.get("saved_deck_info")
        if isinstance(saved_deck, dict):
            self.deck_repo.set_current_deck(saved_deck)
            result["deck_info"] = saved_deck

        window_size = self.settings.get("window_size")
        if isinstance(window_size, list) and len(window_size) == 2:
            result["window_size"] = tuple(window_size)

        screen_pos = self.settings.get("screen_pos")
        if isinstance(screen_pos, list) and len(screen_pos) == 2:
            result["screen_pos"] = tuple(screen_pos)

        return result
