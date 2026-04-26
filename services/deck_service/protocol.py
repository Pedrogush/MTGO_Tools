"""Shared ``self`` contract that the :class:`DeckService` mixins assume."""

from __future__ import annotations

from typing import Any, Protocol

from repositories.deck_repository import DeckRepository
from repositories.metagame_repository import MetagameRepository


class DeckServiceProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckService``."""

    deck_repo: DeckRepository
    metagame_repo: MetagameRepository

    def deck_to_dictionary(self, deck_text: str) -> dict[str, float]: ...
    def analyze_deck(self, deck_content: str) -> dict[str, Any]: ...
    def add_deck_to_buffer(self, buffer: dict[str, float], deck_text: str) -> dict[str, float]: ...
    def render_average_deck(self, buffer: dict[str, float], deck_count: int) -> str: ...
