"""Reusable UI panels for the MTG deck selector application."""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    "CardBoxPanel": "widgets.panels.card_box_panel",
    "CardInspectorPanel": "widgets.panels.card_inspector_panel",
    "CardTablePanel": "widgets.panels.card_table_panel",
    "DeckBuilderPanel": "widgets.panels.deck_builder_panel",
    "DeckNotesPanel": "widgets.panels.deck_notes_panel",
    "DeckResearchPanel": "widgets.panels.deck_research_panel",
    "DeckStatsPanel": "widgets.panels.deck_stats_panel",
    "SideboardGuidePanel": "widgets.panels.sideboard_guide_panel",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str):
    """Lazily import panel modules so headless tests avoid unrelated wx deps."""
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name)
    return getattr(module, name)
