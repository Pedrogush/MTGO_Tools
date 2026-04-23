"""State accessors and i18n helpers for the Top Cards viewer."""

from __future__ import annotations

from utils.i18n import translate


class TopCardsPropertiesMixin:
    """Translation helper for :class:`TopCardsFrame`.

    Kept as a mixin (no ``__init__``) so :class:`TopCardsFrame` remains the
    single source of truth for instance-state initialization.
    """

    _locale: str | None

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)
