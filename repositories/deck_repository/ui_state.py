"""Ephemeral deck state kept in memory for the UI layer."""

from __future__ import annotations

from typing import Any


class UIStateMixin:
    """In-memory deck list, current deck, averaging buffer, and derived helpers."""

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
        # Each unique 75-card configuration gets its own guide; the same exact
        # deck loaded multiple times retains its guide.
        import hashlib

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

    def build_daily_average_deck(
        self,
        decks: list[dict[str, Any]],
        download_func,
        read_func,
        add_to_buffer_func,
        progress_callback=None,
    ) -> dict[str, float]:
        buffer: dict[str, float] = {}
        total = len(decks)
        for index, deck in enumerate(decks, start=1):
            download_func(deck["number"])
            deck_content = read_func()
            buffer = add_to_buffer_func(buffer, deck_content)
            if progress_callback:
                progress_callback(index, total)
        return buffer
