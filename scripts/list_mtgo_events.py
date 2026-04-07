"""List available MTGO events for the current month."""

import sys
from datetime import datetime

from navigators.mtgo_decklists import fetch_decklist_index


def list_events(year: int = None, month: int = None, format_filter: str = None):
    now = datetime.now()
    year = year or now.year
    month = month or now.month

    print(f"\nFetching events for {year}-{month:02d}...")
    entries = fetch_decklist_index(year, month)

    if not entries:
        print("No events found.")
        return

    if format_filter:
        format_filter = format_filter.lower()
        entries = [e for e in entries if e.get("format") and format_filter in e["format"].lower()]
        print(f"\nFound {len(entries)} {format_filter.title()} events:\n")
    else:
        print(f"\nFound {len(entries)} total events:\n")

    for entry in entries:
        fmt = entry.get("format", "Unknown")
        event_type = entry.get("event_type", "other")
        title = entry.get("title", "N/A")
        date = entry.get("publish_date", "N/A")
        url = entry.get("url", "")

        print(f"[{fmt:12s}] {title:40s} ({event_type:15s}) - {date}")
        print(f"             {url}")
        print()


if __name__ == "__main__":
    format_filter = sys.argv[1] if len(sys.argv) > 1 else None

    if format_filter and format_filter.lower() in ["-h", "--help", "help"]:
        print("\nUsage: python list_mtgo_events.py [format]")
        print("\nExamples:")
        print("  python list_mtgo_events.py           # List all events")
        print("  python list_mtgo_events.py modern    # List only Modern events")
        print("  python list_mtgo_events.py legacy    # List only Legacy events")
        print()
    else:
        list_events(format_filter=format_filter)
