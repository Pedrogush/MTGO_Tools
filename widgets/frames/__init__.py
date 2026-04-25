"""Top-level frame windows for the MTG deck selector application."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "AppFrame": "widgets.frames.app_frame",
    "LoadingFrame": "widgets.frames.splash_frame",
    "ManaKeyboardFrame": "widgets.frames.mana_keyboard",
    "MatchHistoryFrame": "widgets.frames.match_history",
    "MetagameAnalysisFrame": "widgets.frames.metagame_analysis",
    "MTGOpponentDeckSpy": "widgets.frames.identify_opponent",
    "RadarFrame": "widgets.frames.radar",
    "RadarPanel": "widgets.frames.radar",
    "TimerAlertFrame": "widgets.frames.timer_alert",
    "TopCardsFrame": "widgets.frames.top_cards",
    "open_mana_keyboard": "widgets.frames.mana_keyboard",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    """Lazily import frame modules so headless tests avoid unrelated wx deps."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    return getattr(module, name)
