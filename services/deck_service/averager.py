"""Averaging helpers for decks."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from services.deck_service.parser import DeckParserMixin

if TYPE_CHECKING:
    from services.deck_service.protocol import DeckServiceProto

    _Base = DeckServiceProto
else:
    _Base = object

_COPY_SEP = "\x00"
KARSTEN_MAIN_SIZE = 60
KARSTEN_SIDE_SIZE = 15


class DeckAveragerMixin(_Base):
    """Aggregate and render average decks."""

    def add_deck_to_buffer(self, buffer: dict[str, float], deck_text: str) -> dict[str, float]:
        deck_dict = self.deck_to_dictionary(deck_text)

        for card_name, count in deck_dict.items():
            buffer[card_name] = buffer.get(card_name, 0.0) + float(count)

        return buffer

    def add_deck_to_karsten_buffer(self, buffer: dict[str, int], deck_text: str) -> dict[str, int]:
        """Build a Karsten unique-copy frequency buffer.

        Each copy of a card (e.g. the 2nd Island) gets its own key.  The value
        is the number of decks that contained at least that many copies.
        """
        deck_dict = self.deck_to_dictionary(deck_text)
        for card_name, count in deck_dict.items():
            for copy_num in range(1, int(count) + 1):
                key = f"{card_name}{_COPY_SEP}{copy_num}"
                buffer[key] = buffer.get(key, 0) + 1
        return buffer

    def render_average_deck(self, buffer: dict[str, float], deck_count: int) -> str:
        if not buffer or deck_count <= 0:
            return ""

        mainboard_lines = []
        sideboard_lines = []

        sorted_cards = sorted(buffer.items(), key=lambda kv: (kv[0].startswith("Sideboard"), kv[0]))

        for card, total in sorted_cards:
            average = float(total) / deck_count

            if average.is_integer():
                value = str(int(average))
            else:
                value = f"{average:.2f}"

            display_name = card.replace("Sideboard ", "")
            output = f"{value} {display_name}"

            if card.startswith("Sideboard"):
                sideboard_lines.append(output)
            else:
                mainboard_lines.append(output)

        lines = mainboard_lines
        if sideboard_lines:
            lines.append("")
            lines.extend(sideboard_lines)

        return "\n".join(lines)

    def render_karsten_deck(
        self,
        buffer: dict[str, int],
        main_size: int = KARSTEN_MAIN_SIZE,
        side_size: int = KARSTEN_SIDE_SIZE,
    ) -> str:
        """Render a Karsten-method average deck from a unique-copy buffer.

        Selects the *main_size* most-present mainboard unique copies and the
        *side_size* most-present sideboard unique copies, then collapses them
        back to normal card counts.
        """
        if not buffer:
            return ""

        main_copies: list[tuple[str, int]] = []
        side_copies: list[tuple[str, int]] = []
        for key, freq in buffer.items():
            card_name, _ = key.rsplit(_COPY_SEP, 1)
            if card_name.startswith("Sideboard "):
                side_copies.append((key, freq))
            else:
                main_copies.append((key, freq))

        def _top_to_counts(copies: list[tuple[str, int]], size: int) -> dict[str, int]:
            top = sorted(copies, key=lambda kv: -kv[1])[:size]
            counts: dict[str, int] = {}
            for key, _ in top:
                card_name, _ = key.rsplit(_COPY_SEP, 1)
                counts[card_name] = counts.get(card_name, 0) + 1
            return counts

        main_counts = _top_to_counts(main_copies, main_size)
        side_counts = _top_to_counts(side_copies, side_size)

        lines = [f"{cnt} {name}" for name, cnt in sorted(main_counts.items())]
        if side_counts:
            lines.append("")
            lines.extend(
                f"{cnt} {name.replace('Sideboard ', '')}"
                for name, cnt in sorted(side_counts.items())
            )
        return "\n".join(lines)

    def filter_today_decks(
        self, decks: list[dict[str, Any]], today: str | None = None
    ) -> list[dict[str, Any]]:
        today = today or time.strftime("%Y-%m-%d").lower()
        return [deck for deck in decks if today in str(deck.get("date", "")).lower()]


class DeckAverager(DeckParserMixin, DeckAveragerMixin):
    """Standalone averager bundling the parser surface for direct instantiation."""
