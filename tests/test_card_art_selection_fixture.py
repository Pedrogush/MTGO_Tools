from __future__ import annotations

import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "card_art_selection"
COLOR_ORDER = "WUBRG"


def _load_json(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _color_key(printing: dict) -> str:
    identity = set(printing.get("color_identity") or [])
    return "".join(color for color in COLOR_ORDER if color in identity)


def test_card_art_selection_fixture_is_complete() -> None:
    manifest = _load_json("manifest.json")
    index = _load_json("printings_index.json")
    cards = _load_json("scryfall_cards.json")

    assert cards
    assert manifest["printing_count"] == len(cards)
    assert manifest["full_art_printing_count"] > 0
    assert manifest["image_file_count"] == manifest["printing_count"] * len(manifest["image_sizes"])
    assert (
        manifest["copied_cached_image_count"] + manifest["generated_placeholder_image_count"]
        == manifest["image_file_count"]
    )
    assert manifest["copied_cached_image_count"] >= manifest["printing_count"]

    printings_by_name = index["data"]
    expected_names = {
        name.lower() for group in manifest["categories"].values() for name in group.values()
    }
    assert set(printings_by_name) == expected_names

    for group_name, group in manifest["categories"].items():
        for expected_identity, card_name in group.items():
            printings = printings_by_name[card_name.lower()]
            assert printings, f"{group_name}:{expected_identity} has no printings"
            for printing in printings:
                if group_name == "colorless":
                    assert _color_key(printing) == ""
                    assert "Land" not in (printing.get("type_line") or "")
                elif group_name == "nonbasic_land":
                    assert "Land" in (printing.get("type_line") or "")
                    assert "Basic" not in (printing.get("type_line") or "")
                else:
                    assert _color_key(printing) == expected_identity

                for image_path in printing["image_uris"].values():
                    path = FIXTURE_DIR / image_path
                    assert path.exists(), f"missing image fixture: {path}"
                    assert not image_path.startswith(("http://", "https://"))

                assert set(printing["fixture_image_sources"]) == set(printing["image_uris"])
                assert printing["fixture_image_sources"]["normal"] != "generated_placeholder"

    assert any(
        printing["full_art"] for printings in printings_by_name.values() for printing in printings
    )
    assert any(
        not printing["full_art"]
        for printings in printings_by_name.values()
        for printing in printings
    )
