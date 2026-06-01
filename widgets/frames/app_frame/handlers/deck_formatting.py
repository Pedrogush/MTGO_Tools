"""Stateless deck/event string formatting helpers for the app-frame handlers.

These are pure functions with no ``self`` dependency, factored out of the
former ``app_events`` god-handler so the behaviour-bearing mixins stay small.
"""

from __future__ import annotations

import re
from typing import Any

from widgets.panels.deck_research_panel.results_filter import (
    _classify_event_type,
    _normalize_date,
)

# Re-exported under their original names so existing references keep working.
normalize_date = _normalize_date
classify_event_type = _classify_event_type


def strip_extra_dates(value: str) -> str:
    if not value:
        return ""
    matches = list(re.finditer(r"\d{4}-\d{2}-\d{2}", value))
    if not matches:
        return value
    result = value
    for match in reversed(matches):
        start, end = match.span()
        prefix_start = start
        while prefix_start > 0 and result[prefix_start - 1] in " -–—|/":
            prefix_start -= 1
        suffix_end = end
        while suffix_end < len(result) and result[suffix_end] in " -–—|/":
            suffix_end += 1
        result = f"{result[:prefix_start].rstrip()} {result[suffix_end:].lstrip()}"
    return " ".join(result.split())


def format_deck_name(deck: dict[str, Any]) -> str:
    date = normalize_date(deck.get("date", ""))
    player = deck.get("player", "")
    event = strip_extra_dates(deck.get("event", ""))
    result = deck.get("result", "")
    line_parts = [part for part in (player, result, date) if part]
    line_one = ", ".join(line_parts) if line_parts else "Unknown"
    line_two = event
    return f"{line_one} | {line_two}".strip(" |")


def format_deck_list_entry(deck: dict[str, Any], show_source: bool = False) -> str:
    date = normalize_date(deck.get("date", ""))
    player = deck.get("player", "")
    event = strip_extra_dates(deck.get("event", ""))
    result = deck.get("result", "")
    line_parts = [part for part in (player, result, date) if part]
    line_one = ", ".join(line_parts) if line_parts else "Unknown"
    if show_source:
        source = deck.get("source", "")
        emoji = "🐠" if source == "mtggoldfish" else "🧙🏾‍♂️"
        line_one = f"{emoji} {line_one}"
    line_two = event
    return f"{line_one}\n{line_two}".strip()


def simple_summary_html(text: str) -> str:
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    escaped = escaped.replace("\n", "<br>")
    return (
        '<html><body bgcolor="#22272E" text="#ECECEC">'
        f'<font size="2">{escaped}</font>'
        "</body></html>"
    )
