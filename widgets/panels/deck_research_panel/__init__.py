"""Deck research panel package."""

from __future__ import annotations

from importlib import import_module

__all__ = ["DeckResearchPanel"]


def __getattr__(name: str):
    """Lazily import the wx panel so importing this package (e.g. for
    ``results_filter``) does not load wx until the panel is actually used."""
    if name == "DeckResearchPanel":
        module = import_module("widgets.panels.deck_research_panel.frame")
        return module.DeckResearchPanel
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
