"""Search Service package — business logic for card search and filtering.

Split by responsibility into internal modules:

- ``basic_search``: name lookups and typeahead suggestions
- ``filtering``: per-card predicate filters and the combined ``filter_cards`` pipeline
- ``builder_search``: deck-builder multi-filter search
- ``deck_search``: deck-text search and card-type grouping
- ``service``: :class:`SearchService` composed from the above mixins
"""

from __future__ import annotations

from services.search_service.service import SearchService

_default_service: SearchService | None = None


def get_search_service() -> SearchService:
    """Get the default search service instance."""
    global _default_service
    if _default_service is None:
        _default_service = SearchService()
    return _default_service


def reset_search_service() -> None:
    """Reset the global search service (use in tests for isolation)."""
    global _default_service
    _default_service = None


__all__ = [
    "SearchService",
    "get_search_service",
    "reset_search_service",
]
