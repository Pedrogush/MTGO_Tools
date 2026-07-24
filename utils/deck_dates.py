"""Repair for impossible "future" deck dates coming from upstream sources.

Decklists record results of events that already happened, so a deck date
beyond tomorrow is always an upstream data-entry error. The dominant failure
is a day/month transposition on paper events entered in DD/MM locales (e.g.
an April 11 store qualifier published as ``2026-11-04``). When both fields
are <= 12 the swap is invisible to format-based parsing and can only be
detected by the future-date impossibility itself, which is what this module
keys on.
"""

from __future__ import annotations

from datetime import date, timedelta

# Deck dates are calendar days with no timezone; a source running ahead of the
# local clock can legitimately stamp "tomorrow", so only dates beyond that are
# treated as impossible.
_FUTURE_TOLERANCE = timedelta(days=1)


def repair_future_date(iso_date: str, today: date | None = None) -> str:
    """Return *iso_date* with an impossible future date repaired or blanked.

    - Not a well-formed ``YYYY-MM-DD`` string, or a date on or before
      tomorrow: returned unchanged.
    - Beyond tomorrow, and swapping day/month yields a valid non-future
      date: the swapped ISO date is returned.
    - Beyond tomorrow and unrepairable: ``""`` is returned — an unknown
      date is less wrong than a future one.
    """
    if not iso_date:
        return iso_date
    try:
        parsed = date.fromisoformat(iso_date)
    except ValueError:
        return iso_date
    horizon = (today or date.today()) + _FUTURE_TOLERANCE
    if parsed <= horizon:
        return iso_date
    try:
        swapped = date(parsed.year, parsed.day, parsed.month)
    except ValueError:
        return ""
    if swapped <= horizon:
        return swapped.isoformat()
    return ""
