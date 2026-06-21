"""Tests for the wx-free sideboard-guide CSV codec."""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from widgets.frames.app_frame.handlers.sideboard_guide_csv import (
    export_guide_to_csv,
    import_guide_from_csv,
)


def _read_rows(path: Path) -> list[list[str]]:
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.reader(fh))


def test_export_builds_matrix_and_decklist(tmp_path: Path) -> None:
    entries = [
        {
            "archetype": "Burn",
            "play_out": {"Negate": 1},
            "play_in": {"Pyroblast": 2},
            "draw_out": {},
            "draw_in": {},
        }
    ]
    zone_cards = {
        "main": [{"name": "Negate", "qty": 3}],
        "side": [{"name": "Pyroblast", "qty": 2}],
    }

    out = tmp_path / "guide.csv"
    export_guide_to_csv(entries, [], zone_cards, str(out))

    rows = _read_rows(out)
    header = rows[0]
    assert header[0] == "Card"
    assert "Burn (Play)" in header

    play_col = header.index("Burn (Play)")
    cells = {row[0]: row[play_col] for row in rows[1:] if row and row[0] in {"Negate", "Pyroblast"}}
    assert cells["Negate"] == "Out 1"
    assert cells["Pyroblast"] == "In 2"

    assert ["DECKLIST"] in rows
    assert ["Mainboard"] in rows
    assert ["3 Negate"] in rows
    assert ["Sideboard"] in rows
    assert ["2 Pyroblast"] in rows


def test_export_respects_exclusions(tmp_path: Path) -> None:
    entries = [
        {
            "archetype": "Burn",
            "play_out": {"Negate": 1},
            "play_in": {},
            "draw_out": {},
            "draw_in": {},
        },
    ]
    out = tmp_path / "guide.csv"
    with pytest.raises(ValueError):
        export_guide_to_csv(entries, ["Burn"], {"main": [], "side": []}, str(out))


def test_export_raises_when_nothing_to_export(tmp_path: Path) -> None:
    out = tmp_path / "guide.csv"
    with pytest.raises(ValueError):
        export_guide_to_csv([], [], {"main": [], "side": []}, str(out))


def test_import_roundtrips_export(tmp_path: Path) -> None:
    entries = [
        {
            "archetype": "Burn",
            "play_out": {"Negate": 1},
            "play_in": {"Pyroblast": 2},
            "draw_out": {},
            "draw_in": {},
        }
    ]
    zone_cards = {
        "main": [{"name": "Negate", "qty": 3}],
        "side": [{"name": "Pyroblast", "qty": 2}],
    }
    path = tmp_path / "guide.csv"
    export_guide_to_csv(entries, [], zone_cards, str(path))

    imported, warnings = import_guide_from_csv(
        file_path=str(path), mainboard_names={"Negate"}, sideboard_names={"Pyroblast"}
    )
    assert warnings == []
    assert len(imported) == 1
    entry = imported[0]
    assert entry["archetype"] == "Burn"
    assert entry["play_out"] == {"Negate": 1}
    assert entry["play_in"] == {"Pyroblast": 2}
    assert entry["notes"] == ""


def test_import_warns_on_missing_cards(tmp_path: Path) -> None:
    path = tmp_path / "guide.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Card", "Burn (Play)"])
        writer.writerow(["Negate", "Out 1"])
        writer.writerow(["Pyroblast", "In 2"])

    imported, warnings = import_guide_from_csv(
        str(path), mainboard_names=set(), sideboard_names=set()
    )
    assert imported == [] or all(not e["play_out"] and not e["play_in"] for e in imported)
    assert warnings
    assert "Negate (not in mainboard)" in warnings[0]
    assert "Pyroblast (not in sideboard)" in warnings[0]


def test_import_rejects_bad_header(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["NotCard", "Burn (Play)"])
    with pytest.raises(ValueError):
        import_guide_from_csv(str(path), set(), set())


def test_import_stops_at_decklist_section(tmp_path: Path) -> None:
    path = tmp_path / "guide.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["Card", "Burn (Play)"])
        writer.writerow(["Negate", "Out 1"])
        writer.writerow(["DECKLIST"])
        writer.writerow(["Mainboard"])
        writer.writerow(["3 Negate"])

    imported, _ = import_guide_from_csv(
        str(path), mainboard_names={"Negate"}, sideboard_names=set()
    )
    assert len(imported) == 1
    assert imported[0]["play_out"] == {"Negate": 1}
