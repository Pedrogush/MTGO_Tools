"""Deck research panel package."""

from __future__ import annotations

from importlib import import_module

__all__ = ["DeckResearchPanel"]


def __getattr__(name: str):
    """Lazily import the wx panel so headless modules in this package
    (e.g. ``results_filter``) can be imported without pulling in wx."""
    if name == "DeckResearchPanel":
        module = import_module("widgets.panels.deck_research_panel.frame")
        return module.DeckResearchPanel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
