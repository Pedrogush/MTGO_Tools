"""State accessors, i18n plumbing, and delegation properties for the main application frame."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from loguru import logger

from utils.i18n import translate

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class AppFramePropertiesMixin(_Base):
    """Translation helper, status setter, and delegation getters for :class:`AppFrame`.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    # ------------------------------------------------------------------ Controller state delegation properties ---------------------------------
    @property
    def current_format(self) -> str:
        return self.controller.current_format

    @current_format.setter
    def current_format(self, value: str) -> None:
        self.controller.current_format = value

    @property
    def archetypes(self) -> list[dict[str, Any]]:
        return self.controller.archetypes

    @archetypes.setter
    def archetypes(self, value: list[dict[str, Any]]) -> None:
        self.controller.archetypes = value

    @property
    def filtered_archetypes(self) -> list[dict[str, Any]]:
        return self.controller.filtered_archetypes

    @filtered_archetypes.setter
    def filtered_archetypes(self, value: list[dict[str, Any]]) -> None:
        self.controller.filtered_archetypes = value

    @property
    def zone_cards(self) -> dict[str, list[dict[str, Any]]]:
        return self.controller.zone_cards

    @zone_cards.setter
    def zone_cards(self, value: dict[str, list[dict[str, Any]]]) -> None:
        self.controller.zone_cards = value

    @property
    def left_mode(self) -> str:
        return self.controller.left_mode

    @left_mode.setter
    def left_mode(self, value: str) -> None:
        self.controller.left_mode = value

    @property
    def loading_archetypes(self) -> bool:
        return self.controller.loading_archetypes

    @loading_archetypes.setter
    def loading_archetypes(self, value: bool) -> None:
        self.controller.loading_archetypes = value

    @property
    def loading_decks(self) -> bool:
        return self.controller.loading_decks

    @loading_decks.setter
    def loading_decks(self, value: bool) -> None:
        self.controller.loading_decks = value

    @property
    def loading_daily_average(self) -> bool:
        return self.controller.loading_daily_average

    @loading_daily_average.setter
    def loading_daily_average(self, value: bool) -> None:
        self.controller.loading_daily_average = value

    @property
    def _loading_lock(self) -> threading.Lock:
        return self.controller._loading_lock

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self.locale, key, **kwargs)

    def _set_status(self, key: str, **kwargs: object) -> None:
        if self.status_bar:
            self.status_bar.SetStatusText(self._t(key, **kwargs))
        logger.info(translate("en", key, **kwargs))

    # ------------------------------------------------------------------ Delegation properties for deck results widgets --------------------------
    @property
    def deck_list(self):  # type: ignore[override]
        return self.research_panel.deck_list

    @property
    def summary_text(self):  # type: ignore[override]
        return self.research_panel.summary_text

    @property
    def deck_action_buttons(self):  # type: ignore[override]
        return self.research_panel.deck_action_buttons

    @property
    def daily_average_button(self):  # type: ignore[override]
        return self.research_panel.daily_average_button

    @property
    def copy_button(self):  # type: ignore[override]
        return self.research_panel.copy_button

    @property
    def load_button(self):  # type: ignore[override]
        return self.research_panel.load_button

    @property
    def save_button(self):  # type: ignore[override]
        return self.research_panel.save_button

    def _has_deck_loaded(self) -> bool:
        return bool(self.zone_cards["main"] or self.zone_cards["side"])
