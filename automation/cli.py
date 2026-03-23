#!/usr/bin/env python3
"""
Command-line interface for controlling the MTGO Tools application.

Usage:
    python -m automation.cli ping
    python -m automation.cli screenshot --path output.png
    python -m automation.cli status
    python -m automation.cli set-format Modern
    python -m automation.cli list-archetypes
    python -m automation.cli select-archetype --name "UR Murktide"
    python -m automation.cli list-decks
    python -m automation.cli select-deck 0
    python -m automation.cli get-deck
    python -m automation.cli switch-tab Stats
"""

import argparse
import json
import sys
from typing import Any

from automation.client import AutomationClient, AutomationError, ConnectionError
from automation.server import DEFAULT_PORT


def format_output(data: Any, as_json: bool = False) -> str:
    """Format data for output."""
    if as_json:
        return json.dumps(data, indent=2)
    if isinstance(data, dict):
        lines = []
        for key, value in data.items():
            if isinstance(value, dict):
                lines.append(f"{key}:")
                for k, v in value.items():
                    lines.append(f"  {k}: {v}")
            elif isinstance(value, list):
                lines.append(f"{key}: ({len(value)} items)")
                for item in value[:10]:  # Limit to first 10
                    if isinstance(item, dict):
                        lines.append(f"  - {item.get('name', item.get('text', str(item)))}")
                    else:
                        lines.append(f"  - {item}")
                if len(value) > 10:
                    lines.append(f"  ... and {len(value) - 10} more")
            else:
                lines.append(f"{key}: {value}")
        return "\n".join(lines)
    return str(data)


def cmd_ping(client: AutomationClient, args: argparse.Namespace) -> int:
    """Ping the server."""
    result = client.ping()
    print(format_output(result, args.json))
    return 0


def cmd_screenshot(client: AutomationClient, args: argparse.Namespace) -> int:
    """Take a screenshot."""
    result = client.screenshot(args.path)
    print(format_output(result, args.json))
    return 0


def cmd_status(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get status bar text."""
    status = client.get_status()
    if args.json:
        print(json.dumps({"status": status}))
    else:
        print(f"Status: {status}")
    return 0


def cmd_window_info(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get window information."""
    result = client.get_window_info()
    print(format_output(result, args.json))
    return 0


def cmd_list_widgets(client: AutomationClient, args: argparse.Namespace) -> int:
    """List available widgets."""
    result = client.list_widgets()
    print(format_output(result, args.json))
    return 0


def cmd_click(client: AutomationClient, args: argparse.Namespace) -> int:
    """Click a button."""
    result = client.click(args.widget, args.label)
    print(format_output(result, args.json))
    return 0 if result.get("clicked") else 1


def cmd_set_format(client: AutomationClient, args: argparse.Namespace) -> int:
    """Set the current format."""
    result = client.set_format(args.format)
    print(format_output(result, args.json))
    return 0


def cmd_get_format(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get the current format."""
    format_name = client.get_format()
    if args.json:
        print(json.dumps({"format": format_name}))
    else:
        print(f"Format: {format_name}")
    return 0


def cmd_list_archetypes(client: AutomationClient, args: argparse.Namespace) -> int:
    """List available archetypes."""
    archetypes = client.get_archetypes()
    if args.json:
        print(json.dumps({"archetypes": archetypes}))
    else:
        if not archetypes:
            print("No archetypes loaded. Try fetching archetypes first.")
            return 1
        print(f"Archetypes ({len(archetypes)}):")
        for i, arch in enumerate(archetypes):
            print(f"  {i}: {arch.get('name', 'Unknown')}")
    return 0


def cmd_select_archetype(client: AutomationClient, args: argparse.Namespace) -> int:
    """Select an archetype."""
    kwargs = {}
    if args.index is not None:
        kwargs["index"] = args.index
    if args.name is not None:
        kwargs["name"] = args.name

    result = client.select_archetype(**kwargs)
    print(format_output(result, args.json))
    return 0 if result.get("selected") else 1


def cmd_list_decks(client: AutomationClient, args: argparse.Namespace) -> int:
    """List decks in the deck list."""
    decks = client.get_deck_list()
    if args.json:
        print(json.dumps({"decks": decks}))
    else:
        if not decks:
            print("No decks loaded. Select an archetype first.")
            return 1
        print(f"Decks ({len(decks)}):")
        for deck in decks:
            print(f"  {deck.get('index', '?')}: {deck.get('text', 'Unknown')}")
    return 0


def cmd_select_deck(client: AutomationClient, args: argparse.Namespace) -> int:
    """Select a deck."""
    result = client.select_deck(args.index)
    print(format_output(result, args.json))
    return 0 if result.get("selected") else 1


def cmd_get_deck(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get the current deck text."""
    deck_text = client.get_deck_text()
    if args.json:
        print(json.dumps({"deck_text": deck_text}))
    else:
        if not deck_text:
            print("No deck loaded.")
            return 1
        print(deck_text)
    return 0


def cmd_switch_tab(client: AutomationClient, args: argparse.Namespace) -> int:
    """Switch to a tab."""
    result = client.switch_tab(args.tab)
    print(format_output(result, args.json))
    return 0 if result.get("switched") else 1


def cmd_wait(client: AutomationClient, args: argparse.Namespace) -> int:
    """Wait for a specified time."""
    client.wait(args.ms)
    if not args.json:
        print(f"Waited {args.ms}ms")
    return 0


def cmd_load_deck(client: AutomationClient, args: argparse.Namespace) -> int:
    """Load a deck from a text file or inline text."""
    if args.file:
        import os

        if not os.path.exists(args.file):
            print(f"File not found: {args.file}", file=sys.stderr)
            return 1
        with open(args.file, encoding="utf-8") as f:
            deck_text = f.read()
    else:
        deck_text = args.text or ""
    result = client.load_deck_text(deck_text)
    print(format_output(result, args.json))
    return 0 if result.get("loaded") else 1


def cmd_get_zone_cards(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get cards in a zone."""
    result = client.get_zone_cards(args.zone)
    if args.json:
        print(format_output(result, True))
    else:
        zone = result.get("zone", args.zone)
        cards = result.get("cards", [])
        total = result.get("total_qty", 0)
        print(f"{zone.title()} ({total} cards):")
        for card in cards:
            print(f"  {card['qty']}x {card['name']}")
    return 0


def cmd_add_card(client: AutomationClient, args: argparse.Namespace) -> int:
    """Add a card to a zone."""
    result = client.add_card_to_zone(args.zone, args.name, args.qty)
    print(format_output(result, args.json))
    return 0 if result.get("added") else 1


def cmd_remove_card(client: AutomationClient, args: argparse.Namespace) -> int:
    """Remove (subtract) a card from a zone."""
    result = client.subtract_card_from_zone(args.zone, args.name, args.qty)
    print(format_output(result, args.json))
    return 0 if result.get("subtracted") else 1


def cmd_get_scroll_pos(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get scroll position of a zone."""
    result = client.get_scroll_pos(args.zone)
    print(format_output(result, args.json))
    return 0


def cmd_get_builder_results(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get builder search result count."""
    result = client.get_builder_result_count()
    print(format_output(result, args.json))
    return 0


def cmd_get_builder_top_item(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get the index of the topmost visible item in builder search results."""
    result = client.get_builder_top_item()
    print(format_output(result, args.json))
    return 0


def cmd_open_widget(client: AutomationClient, args: argparse.Namespace) -> int:
    """Open a widget window."""
    result = client.open_widget(args.widget_name)
    print(format_output(result, args.json))
    return 0 if result.get("opened") else 1


def cmd_get_deck_notes(client: AutomationClient, args: argparse.Namespace) -> int:
    """Get the current deck notes cards."""
    result = client.get_deck_notes()
    print(format_output(result, args.json))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Control the MTGO Tools application from the command line.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s ping                                    Check if app is running
  %(prog)s screenshot --path test.png              Take a screenshot
  %(prog)s status                                  Get status bar text
  %(prog)s set-format Modern                       Set format to Modern
  %(prog)s list-archetypes                         List available archetypes
  %(prog)s select-archetype --name "UR Murktide"   Select an archetype
  %(prog)s list-decks                              List decks for archetype
  %(prog)s select-deck 0                           Select first deck
  %(prog)s get-deck                                Print current deck
  %(prog)s switch-tab Stats                        Switch to Stats tab
        """,
    )

    parser.add_argument("--host", default="127.0.0.1", help="Server host (default: 127.0.0.1)")
    parser.add_argument(
        "--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})"
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--timeout", type=float, default=30.0, help="Command timeout in seconds")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # ping
    subparsers.add_parser("ping", help="Check if the server is responding")

    # screenshot
    p = subparsers.add_parser("screenshot", help="Take a screenshot")
    p.add_argument("--path", "-p", help="Path to save screenshot (default: auto-generated)")

    # status
    subparsers.add_parser("status", help="Get status bar text")

    # window-info
    subparsers.add_parser("window-info", help="Get window information")

    # list-widgets
    subparsers.add_parser("list-widgets", help="List available widgets")

    # click
    p = subparsers.add_parser("click", help="Click a button")
    p.add_argument("widget", help="Widget name")
    p.add_argument("--label", "-l", help="Button label within widget")

    # set-format
    p = subparsers.add_parser("set-format", help="Set the current format")
    p.add_argument("format", help="Format name (e.g., Modern, Standard)")

    # get-format
    subparsers.add_parser("get-format", help="Get the current format")

    # list-archetypes
    subparsers.add_parser("list-archetypes", help="List available archetypes")

    # select-archetype
    p = subparsers.add_parser("select-archetype", help="Select an archetype")
    p.add_argument("--index", "-i", type=int, help="Archetype index")
    p.add_argument("--name", "-n", help="Archetype name")

    # list-decks
    subparsers.add_parser("list-decks", help="List decks in deck list")

    # select-deck
    p = subparsers.add_parser("select-deck", help="Select a deck by index")
    p.add_argument("index", type=int, help="Deck index")

    # get-deck
    subparsers.add_parser("get-deck", help="Get current deck text")

    # switch-tab
    p = subparsers.add_parser("switch-tab", help="Switch to a specific tab")
    p.add_argument("tab", help="Tab name (e.g., 'Deck Tables', 'Stats', 'Sideboard Guide')")

    # wait
    p = subparsers.add_parser("wait", help="Wait for specified milliseconds")
    p.add_argument("ms", type=int, help="Milliseconds to wait")

    # load-deck
    p = subparsers.add_parser("load-deck", help="Load a deck from text or file")
    p.add_argument("--text", "-t", help="Deck text inline")
    p.add_argument("--file", "-f", help="Path to deck text file")

    # get-zone-cards
    p = subparsers.add_parser("get-zone-cards", help="Get cards in a zone")
    p.add_argument("--zone", "-z", default="main", help="Zone: main, side, or out (default: main)")

    # add-card
    p = subparsers.add_parser("add-card", help="Add a card to a zone")
    p.add_argument("--zone", "-z", default="main", help="Zone: main or side (default: main)")
    p.add_argument("--name", "-n", required=True, help="Card name")
    p.add_argument("--qty", "-q", type=int, default=1, help="Quantity to add (default: 1)")

    # remove-card
    p = subparsers.add_parser("remove-card", help="Remove (subtract) a card from a zone")
    p.add_argument("--zone", "-z", default="main", help="Zone: main or side (default: main)")
    p.add_argument("--name", "-n", required=True, help="Card name")
    p.add_argument("--qty", "-q", type=int, default=1, help="Quantity to remove (default: 1)")

    # get-scroll-pos
    p = subparsers.add_parser("get-scroll-pos", help="Get scroll position of a zone table")
    p.add_argument("--zone", "-z", default="main", help="Zone: main, side, or out (default: main)")

    # get-builder-results
    subparsers.add_parser("get-builder-results", help="Get builder search result count")

    # open-widget
    p = subparsers.add_parser("open-widget", help="Open a widget window")
    p.add_argument(
        "widget_name",
        choices=["opponent_tracker", "match_history", "timer_alert", "metagame"],
        help="Widget to open",
    )

    # get-deck-notes
    subparsers.add_parser("get-deck-notes", help="Get the current deck notes")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Map commands to handlers
    handlers = {
        "ping": cmd_ping,
        "screenshot": cmd_screenshot,
        "status": cmd_status,
        "window-info": cmd_window_info,
        "list-widgets": cmd_list_widgets,
        "click": cmd_click,
        "set-format": cmd_set_format,
        "get-format": cmd_get_format,
        "list-archetypes": cmd_list_archetypes,
        "select-archetype": cmd_select_archetype,
        "list-decks": cmd_list_decks,
        "select-deck": cmd_select_deck,
        "get-deck": cmd_get_deck,
        "switch-tab": cmd_switch_tab,
        "wait": cmd_wait,
        "load-deck": cmd_load_deck,
        "get-zone-cards": cmd_get_zone_cards,
        "add-card": cmd_add_card,
        "remove-card": cmd_remove_card,
        "get-scroll-pos": cmd_get_scroll_pos,
        "get-builder-results": cmd_get_builder_results,
        "get-builder-top-item": cmd_get_builder_top_item,
        "open-widget": cmd_open_widget,
        "get-deck-notes": cmd_get_deck_notes,
    }

    handler = handlers.get(args.command)
    if handler is None:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        return 1

    try:
        client = AutomationClient(host=args.host, port=args.port, timeout=args.timeout)
        return handler(client, args)
    except ConnectionError as e:
        print(f"Connection error: {e}", file=sys.stderr)
        print("Make sure the application is running with automation enabled.", file=sys.stderr)
        return 1
    except AutomationError as e:
        print(f"Automation error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
