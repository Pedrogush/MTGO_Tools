"""State accessors, i18n plumbing, and delegation properties for the main application frame."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
