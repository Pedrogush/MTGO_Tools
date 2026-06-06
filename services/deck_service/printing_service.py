"""DeckService mixin exposing the printing-conversion helpers as methods.

Thin delegation to the pure functions in :mod:`services.deck_service.printing`
so callers holding a :class:`DeckService` can convert decklists between
printing selections without importing the module functions directly.
"""

from __future__ import annotations

from typing import Any

from services.deck_service import printing
from services.deck_service.printing import ParsedCard, PrintingIndex


class DeckPrintingMixin:
    """Printing-aware decklist parsing and conversion."""

    def parse_printed_decklist(self, text: str, index: PrintingIndex) -> list[ParsedCard]:
        return printing.parse_printed_decklist(text, index)

    def format_decklist_on_load(self, text: str, index: PrintingIndex) -> str:
        return printing.format_decklist_on_load(text, index)

    def decklist_with_oldest_printings(self, text: str, index: PrintingIndex) -> str:
        return printing.decklist_with_oldest_printings(text, index)

    def decklist_with_newest_printings(self, text: str, index: PrintingIndex) -> str:
        return printing.decklist_with_newest_printings(text, index)

    def decklist_with_full_art_printings(self, text: str, index: PrintingIndex) -> str:
        return printing.decklist_with_full_art_printings(text, index)

    def decklist_with_newest_printings_by(self, text: str, index: PrintingIndex, when: Any) -> str:
        return printing.decklist_with_newest_printings_by(text, index, when)

    def decklist_with_printings_after(self, text: str, index: PrintingIndex, when: Any) -> str:
        return printing.decklist_with_printings_after(text, index, when)

    def decklist_with_printings_to_agnostic(self, text: str, index: PrintingIndex) -> str:
        return printing.decklist_with_printings_to_agnostic(text, index)
