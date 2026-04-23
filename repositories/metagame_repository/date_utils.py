"""Date parsing utility for deck records from MTGGoldfish and MTGO exports."""

from __future__ import annotations

from datetime import datetime


def _parse_deck_date(date_str: str) -> tuple[int, int, int]:
    """Parse deck dates in YYYY-MM-DD (MTGGoldfish) or MM/DD/YYYY (MTGO) form."""
    if not date_str:
        return (0, 0, 0)

    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            return (parsed.year, parsed.month, parsed.day)
        except (TypeError, ValueError):
            continue

    return (0, 0, 0)
