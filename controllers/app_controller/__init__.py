"""AppController package — application logic for the deck selector window.

Split by responsibility into internal modules:

- ``ui_callbacks``: ``UICallbacks`` dataclass + ``AppControllerUIHelpers`` builder
  that marshals callbacks onto the wx UI thread
- ``card_data``: background card-index preload (``CardDataMixin``)
- ``archetypes``: archetype fetch, deck-list loading, archetype state
  (``ArchetypesMixin``)
- ``decks``: per-deck download/save/build plus daily-average orchestration
  (``DeckManagementMixin``)
- ``collection``: collection cache load + MTGO bridge refresh (``CollectionMixin``)
- ``bulk_data``: Scryfall bulk metadata check, download, and memory load
  (``BulkDataMixin``, folded from the former ``bulk_data_helpers`` module)
- ``settings``: persistent session preferences (``SettingsMixin``)
- ``lifecycle``: startup orchestration, frame factory, shutdown (``LifecycleMixin``)
- ``controller``: :class:`AppController` composed from the above mixins
"""

from __future__ import annotations

from controllers.app_controller.controller import AppController

_controller_instance: AppController | None = None


def get_deck_selector_controller() -> AppController:
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = AppController()
    return _controller_instance


def reset_deck_selector_controller() -> None:
    global _controller_instance
    _controller_instance = None


__all__ = [
    "AppController",
    "get_deck_selector_controller",
    "reset_deck_selector_controller",
]
