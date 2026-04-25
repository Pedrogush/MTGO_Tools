"""Persistent session preferences (format, language, data source, averaging…)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from utils.i18n import normalize_locale

if TYPE_CHECKING:
    from controllers.app_controller.protocol import AppControllerProto

    _Base = AppControllerProto
else:
    _Base = object


class SettingsMixin(_Base):
    """Settings getters/setters that mirror into the ``DeckSelectorSessionManager``."""

    def save_settings(
        self,
        window_size: tuple[int, int] | None = None,
        screen_pos: tuple[int, int] | None = None,
    ) -> None:
        self.session_manager.save(
            current_format=self.current_format,
            left_mode=self.left_mode,
            deck_data_source=self._deck_data_source,
            zone_cards=self.zone_cards,
            window_size=window_size,
            screen_pos=screen_pos,
        )

    def get_deck_data_source(self) -> str:
        return self._deck_data_source

    def set_deck_data_source(self, source: str) -> None:
        if source not in ("mtggoldfish", "mtgo", "both"):
            logger.warning(f"Invalid deck data source: {source}, defaulting to 'both'")
            source = "both"
        if self._deck_data_source == source:
            return
        self._deck_data_source = source
        self.session_manager.update_deck_data_source(source)

    def get_average_method(self) -> str:
        return self._average_method

    def set_average_method(self, method: str) -> None:
        valid = method if method in {"karsten", "arithmetic"} else "karsten"
        if self._average_method == valid:
            return
        self._average_method = valid
        self.session_manager.update_average_method(valid)

    def get_average_hours(self) -> int:
        return self._average_hours

    def set_average_hours(self, hours: int) -> None:
        valid = hours if hours in {12, 24, 36, 48, 60, 72} else 24
        if self._average_hours == valid:
            return
        self._average_hours = valid
        self.session_manager.update_average_hours(valid)

    def get_language(self) -> str:
        return self.current_language

    def set_language(self, language: str) -> None:
        normalized = normalize_locale(language)
        if self.current_language == normalized:
            return
        self.current_language = normalized
        self.session_manager.update_language(normalized)

    def get_event_logging_enabled(self) -> bool:
        return self.event_logger.enabled

    def set_event_logging_enabled(self, enabled: bool) -> None:
        self.event_logger.enabled = enabled
        self.session_manager.update_event_logging_enabled(enabled)

    def get_current_format(self) -> str:
        return self.current_format

    def set_current_format(self, format_name: str) -> None:
        self.current_format = format_name

    def get_left_mode(self) -> str:
        return self.left_mode

    def set_left_mode(self, mode: str) -> None:
        self.left_mode = mode
