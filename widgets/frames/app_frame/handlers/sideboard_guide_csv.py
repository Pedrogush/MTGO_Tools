"""wx-free CSV codec for the sideboard guide.

Pure serialization/parsing for the sideboard-guide matrix format, extracted
from the wx import/export handlers so the matrix-building and regex-parsing
logic is directly unit-testable. No wx dependency.
"""

from __future__ import annotations

import csv
import re
from typing import Any


def export_guide_to_csv(
    entries: list[dict[str, Any]],
    exclusions: list[str],
    zone_cards: dict[str, list[dict[str, Any]]],
    file_path: str,
) -> None:
    """Export a sideboard guide to CSV with smart filtering.

    Rows are cards, columns are matchups (archetype + scenario), cells show
    actions (In/Out) and the decklist is appended after a separator.

    Args:
        entries: Sideboard guide entries.
        exclusions: Archetype names to exclude from export.
        zone_cards: Mapping of zone name ("main"/"side") to card dicts.
        file_path: Destination CSV path.

    Raises:
        ValueError: If no cards remain to export after filtering.
    """
    card_actions: dict[str, dict[str, set[str]]] = {}

    for entry in entries:
        if entry.get("archetype") in exclusions:
            continue

        archetype = entry.get("archetype", "Unknown")
        for scenario, out_key, in_key in [
            ("Play", "play_out", "play_in"),
            ("Draw", "draw_out", "draw_in"),
        ]:
            out_cards = entry.get(out_key, {})
            in_cards = entry.get(in_key, {})

            if isinstance(out_cards, dict):
                for card_name, qty in out_cards.items():
                    if qty > 0:
                        card_actions.setdefault(card_name, {}).setdefault(
                            f"{archetype} ({scenario})", set()
                        ).add(f"Out {qty}")

            if isinstance(in_cards, dict):
                for card_name, qty in in_cards.items():
                    if qty > 0:
                        card_actions.setdefault(card_name, {}).setdefault(
                            f"{archetype} ({scenario})", set()
                        ).add(f"In {qty}")

    filtered_cards = {card: actions for card, actions in card_actions.items() if actions}
    if not filtered_cards:
        raise ValueError("No cards to export after filtering")

    all_matchups = sorted(
        {matchup for actions in filtered_cards.values() for matchup in actions.keys()}
    )

    with open(file_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Card"] + all_matchups)

        for card_name in sorted(filtered_cards.keys()):
            row = [card_name]
            for matchup in all_matchups:
                actions = filtered_cards[card_name].get(matchup, set())
                row.append(" & ".join(sorted(actions)) if actions else "")
            writer.writerow(row)

        writer.writerow([])
        writer.writerow([])
        writer.writerow(["DECKLIST"])
        writer.writerow([])

        writer.writerow(["Mainboard"])
        mainboard_cards = zone_cards.get("main", [])
        for card in sorted(mainboard_cards, key=lambda c: c.get("name", "")):
            writer.writerow([f"{card.get('qty', 0)} {card.get('name', '')}"])

        writer.writerow([])
        writer.writerow(["Sideboard"])
        sideboard_cards = zone_cards.get("side", [])
        for card in sorted(sideboard_cards, key=lambda c: c.get("name", "")):
            writer.writerow([f"{card.get('qty', 0)} {card.get('name', '')}"])


def import_guide_from_csv(
    file_path: str,
    mainboard_names: set[str],
    sideboard_names: set[str],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Import a sideboard guide from CSV format with sanitization.

    Args:
        file_path: Source CSV path.
        mainboard_names: Valid mainboard card names (for "Out" validation).
        sideboard_names: Valid sideboard card names (for "In" validation).

    Returns:
        A tuple of (imported entries, list of warning messages).

    Raises:
        ValueError: If the CSV header is not in the expected format.
    """
    entries_by_archetype: dict[str, dict[str, dict[str, int]]] = {}
    warnings: list[str] = []
    missing_cards: set[str] = set()

    with open(file_path, encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        if not header or header[0] != "Card":
            raise ValueError("Invalid CSV format: expected 'Card' as first column header")

        matchup_columns = header[1:]
        archetype_scenario_map: list[tuple[str | None, str | None]] = []
        for col in matchup_columns:
            match = re.match(r"^(.+?)\s*\((Play|Draw)\)$", col)
            if match:
                archetype_name = match.group(1).strip()
                scenario = match.group(2).lower()
                archetype_scenario_map.append((archetype_name, scenario))
            else:
                archetype_scenario_map.append((None, None))

        for row in reader:
            if not row:
                continue
            if row[0] in ["DECKLIST", "Mainboard", "Sideboard"]:
                break

            card_name = row[0].strip()
            if not card_name:
                continue

            for idx, cell_value in enumerate(row[1:], start=0):
                if idx >= len(archetype_scenario_map):
                    continue
                archetype_name, scenario = archetype_scenario_map[idx]
                if not archetype_name or not scenario:
                    continue
                if not cell_value or not cell_value.strip():
                    continue

                entries_by_archetype.setdefault(
                    archetype_name,
                    {"play_out": {}, "play_in": {}, "draw_out": {}, "draw_in": {}},
                )

                actions = cell_value.split("&")
                for action in actions:
                    action = action.strip()
                    match = re.match(r"^(Out|In)\s+(\d+)$", action)
                    if not match:
                        continue
                    direction = match.group(1).lower()
                    qty = int(match.group(2))
                    key = f"{scenario}_{direction}"

                    if direction == "out" and card_name not in mainboard_names:
                        missing_cards.add(f"{card_name} (not in mainboard)")
                        continue
                    if direction == "in" and card_name not in sideboard_names:
                        missing_cards.add(f"{card_name} (not in sideboard)")
                        continue

                    entries_by_archetype[archetype_name][key][card_name] = qty

    imported_entries = [
        {
            "archetype": archetype_name,
            "play_out": data["play_out"],
            "play_in": data["play_in"],
            "draw_out": data["draw_out"],
            "draw_in": data["draw_in"],
            "notes": "",
        }
        for archetype_name, data in entries_by_archetype.items()
    ]

    if missing_cards:
        warnings.append(f"Cards not in deck: {', '.join(sorted(missing_cards))}")

    return imported_entries, warnings
