from collections import Counter
from typing import Any

from utils.mana_query import tokenize_mana_symbols


def matches_mana_cost(card_cost: str, query: str, mode: str) -> bool:
    query_tokens = tokenize_mana_symbols(query)
    if not query_tokens:
        return True
    card_tokens = tokenize_mana_symbols(card_cost)
    card_counts = Counter(card_tokens)
    query_counts = Counter(query_tokens)
    if mode == "exact":
        return card_counts == query_counts
    for symbol, needed in query_counts.items():
        if card_counts.get(symbol, 0) < needed:
            return False
    return True


def matches_mana_value(card_value: Any, target: float, comparator: str) -> bool:
    try:
        value = float(card_value)
    except (TypeError, ValueError):
        return False
    if comparator == "<":
        return value < target
    if comparator == "≤":
        return value <= target
    if comparator == "=":
        return value == target
    if comparator == "≥":
        return value >= target
    if comparator == ">":
        return value > target
    return True


def matches_color_filter(card_colors: list[str], selected: list[str], mode: str) -> bool:
    if not selected or mode in ("Any", "-"):
        return True
    selected_set = {c.upper() for c in selected}
    card_set = {c.upper() for c in card_colors if c}
    if not card_set:
        card_set = {"C"}
    if mode in ("At least", "≥"):
        return selected_set.issubset(card_set)
    if mode in ("Exactly", "="):
        return card_set == selected_set
    if mode in ("Not these", "≠"):
        return selected_set.isdisjoint(card_set)
    return True
