"""Pure-data helpers and read-only getters for the deck results list."""

from __future__ import annotations


class DeckResultsListPropertiesMixin:
    """Read-only getters and pure-data helpers for :class:`DeckResultsList`.

    Kept as a mixin (no ``__init__``) so :class:`DeckResultsList` remains the
    single source of truth for instance-state initialization.
    """

    _items: list[tuple[bool, tuple]]

    def GetCount(self) -> int:
        return len(self._items)

    def GetString(self, n: int) -> str:
        if n < 0 or n >= len(self._items):
            return ""
        is_structured, data = self._items[n]
        if is_structured:
            emoji, player, archetype, event, result, date = data
            player_arch = f"{player}, {archetype}" if archetype else player
            parts = [p for p in (player_arch, result, date) if p]
            line_one = f"{emoji} {', '.join(parts)}".strip() if emoji else ", ".join(parts)
            return f"{line_one}\n{event}" if event else line_one
        else:
            emoji, line_one, line_two = data
            full_line_one = emoji + line_one if emoji else line_one
            return f"{full_line_one}\n{line_two}" if line_two else full_line_one

    @staticmethod
    def _split_emoji_prefix(line: str) -> tuple[str, str]:
        if not line or ord(line[0]) < 128:
            return "", line
        idx = line.find(" ")
        if idx == -1:
            return line, ""
        return line[: idx + 1], line[idx + 1 :]

    def _split_lines(self, text: str) -> tuple[str, str]:
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return "", ""
        if len(lines) == 1:
            return lines[0], ""
        return lines[0], " ".join(lines[1:])
