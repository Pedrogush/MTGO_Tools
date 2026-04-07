"""Transient workspace state for deck selection and averaging."""

from __future__ import annotations

import hashlib
from typing import Any


class DeckWorkspaceState:
    """In-memory deck workspace state kept separate from persistence stores."""

    def __init__(self) -> None:
        self._decks: list[dict[str, Any]] = []
        self._current_deck: dict[str, Any] | None = None
        self._current_deck_text: str = ""
        self._deck_buffer: dict[str, float] = {}
        self._decks_added: int = 0

    def get_decks_list(self) -> list[dict[str, Any]]:
        return self._decks

    def set_decks_list(self, decks: list[dict[str, Any]]) -> None:
        self._decks = decks

    def clear_decks_list(self) -> None:
        self._decks = []

    def get_current_deck(self) -> dict[str, Any] | None:
        return self._current_deck

    def get_current_deck_key(self) -> str:
        current_deck = self.get_current_deck()
        if current_deck:
            return current_deck.get("href") or current_deck.get("name", "manual").lower()
        return "manual"

    def get_current_decklist_hash(self) -> str:
        deck_text = self.get_current_deck_text()
        if not deck_text:
            return "empty"

        lines = [line.strip() for line in deck_text.strip().split("\n") if line.strip()]
        lines.sort()
        normalized_text = "\n".join(lines)

        hash_obj = hashlib.sha256(normalized_text.encode("utf-8"))
        return hash_obj.hexdigest()[:16]

    def set_current_deck(self, deck: dict[str, Any] | None) -> None:
        self._current_deck = deck

    def get_current_deck_text(self) -> str:
        return self._current_deck_text

    def set_current_deck_text(self, deck_text: str) -> None:
        self._current_deck_text = deck_text

    def get_deck_buffer(self) -> dict[str, float]:
        return self._deck_buffer

    def set_deck_buffer(self, buffer: dict[str, float]) -> None:
        self._deck_buffer = buffer

    def get_decks_added_count(self) -> int:
        return self._decks_added

    def set_decks_added_count(self, count: int) -> None:
        self._decks_added = count

    def reset_averaging_state(self) -> None:
        self._deck_buffer = {}
        self._decks_added = 0
