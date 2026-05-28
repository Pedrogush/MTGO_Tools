"""Date parsing utility for deck records from MTGGoldfish and MTGO exports."""

from __future__ import annotations

from datetime import datetime


def _parse_deck_date(date_str: str) -> tuple[int, int, int]:
    """Parse deck dates into a sortable ``(year, month, day)`` tuple.

    Accepts the canonical YYYY-MM-DD (MTGGoldfish) and MM/DD/YYYY (MTGO)
    forms. Also accepts YYYY-DD-MM as a fallback so misformatted upstream
    rows sort by their true calendar date rather than collapsing to
    ``(0, 0, 0)`` and appearing as the oldest entries (issue #475).
    """
    if not date_str:
        return (0, 0, 0)

    for fmt in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            parsed = datetime.strptime(date_str, fmt)
            return (parsed.year, parsed.month, parsed.day)
        except (TypeError, ValueError):
            continue

    # Fallback: YYYY-DD-MM (some upstream rows arrive in this order).
    # Only accept when the trailing two digits are a valid month (1-12)
    # and the middle two digits are a plausible day (1-31), so we never
    # misinterpret a real YYYY-MM-DD date.
    try:
        parsed = datetime.strptime(date_str, "%Y-%d-%m")
        return (parsed.year, parsed.month, parsed.day)
    except (TypeError, ValueError):
        return (0, 0, 0)
