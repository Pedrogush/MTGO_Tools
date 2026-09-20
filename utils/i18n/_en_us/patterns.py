"""Deck patterns (capability explorer) tab strings. (English (United States))"""

MESSAGES: dict[str, str] = {
    "tabs.deck_patterns": "Patterns",
    "tabs.tooltip.deck_patterns": "What this deck could cast on each turn, off every land combination it can make",
    # Says what the numbers are before anyone reads one: an upper bound, not odds.
    "patterns.ceiling": (
        "Capability ceiling — assumes the whole decklist is in hand and that no "
        "lands, mana or board state carry over between turns. Not a probability."
    ),
    "patterns.turn": "Turn",
    "patterns.turn.tooltip": "Turn N means N lands in play — each turn is evaluated on its own",
    "patterns.refresh": "Recalculate",
    "patterns.combination": "{lands} — {mana} mana",
    "patterns.no_plays": "Nothing castable off this mana",
    "patterns.status.computing": "Calculating…",
    "patterns.status.no_deck": "Load a deck to see what it can do.",
    "patterns.status.no_lands": "No mana-producing lands in the main deck.",
    "patterns.status.summary": "Turn {turn}: {combinations} land combinations, {playable} with a play",
    "patterns.status.truncated": "truncated, showing partial results",
    "patterns.status.failed": "Could not calculate patterns for this deck.",
}
