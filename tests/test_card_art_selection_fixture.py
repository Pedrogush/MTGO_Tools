from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "card_art_selection"
COLOR_ORDER = "WUBRG"

sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import generate_card_art_selection_fixture as generator  # noqa: E402


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

    for card in cards:
        for image_path in card["image_uris"].values():
            assert not image_path.startswith(("http://", "https://"))
            assert (FIXTURE_DIR / image_path).exists(), f"missing rewritten image: {image_path}"
        source_uris = card["source_image_uris"]
        assert source_uris, f"{card.get('name')} missing source_image_uris"
        assert source_uris["normal"].startswith("https://")
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
                    assert _color_key(printing) == ""
                else:
                    assert _color_key(printing) == expected_identity

                for image_path in printing["image_uris"].values():
                    path = FIXTURE_DIR / image_path
                    assert path.exists(), f"missing image fixture: {path}"
                    assert not image_path.startswith(("http://", "https://"))

                assert set(printing["fixture_image_sources"]) == set(printing["image_uris"])
                assert printing["fixture_image_sources"]["normal"] != "generated_placeholder"

    non_placeholder_sources = sum(
        1
        for printings in printings_by_name.values()
        for printing in printings
        for source in printing["fixture_image_sources"].values()
        if source != "generated_placeholder"
    )
    assert non_placeholder_sources == manifest["copied_cached_image_count"]

    assert any(
        printing["full_art"] for printings in printings_by_name.values() for printing in printings
    )
    assert any(
        not printing["full_art"]
        for printings in printings_by_name.values()
        for printing in printings
    )


def test_color_identity_key_orders_by_wubrg() -> None:
    assert generator.color_identity_key({"color_identity": ["G", "W"]}) == "WG"
    assert generator.color_identity_key({"color_identity": ["R", "U", "B"]}) == "UBR"
    assert generator.color_identity_key({}) == ""
    assert generator.color_identity_key({"color_identity": None}) == ""


def test_image_color_mono_and_multicolor() -> None:
    assert generator.image_color({"color_identity": ["W"]}) == generator.COLOR_SWATCHES["W"]
    # Colorless cards fall back to the "C" swatch.
    assert generator.image_color({"color_identity": []}) == generator.COLOR_SWATCHES["C"]
    # Multicolor averages the component swatches channel-by-channel.
    white = generator.COLOR_SWATCHES["W"]
    blue = generator.COLOR_SWATCHES["U"]
    expected = tuple((white[i] + blue[i]) // 2 for i in range(3))
    assert generator.image_color({"color_identity": ["W", "U"]}) == expected


def test_contrast_color_picks_dark_text_on_light_background() -> None:
    assert generator.contrast_color((240, 240, 240)) == (20, 22, 25)
    assert generator.contrast_color((10, 10, 10)) == (245, 245, 240)


def test_wrapped_lines_wraps_and_forces_long_words() -> None:
    assert generator.wrapped_lines("a b c d e", max_chars=3) == ["a b", "c d", "e"]
    # A single word longer than max_chars is forced onto its own line.
    assert generator.wrapped_lines("superlongword tail", max_chars=4) == [
        "superlongword",
        "tail",
    ]
    assert generator.wrapped_lines("", max_chars=10) == []


def test_slugify_handles_punctuation_and_empty() -> None:
    assert generator.slugify("") == "card"
    assert generator.slugify("!!!") == "card"
    assert generator.slugify('Miles "Tails" Prower') == "miles-tails-prower"


def test_build_printing_record_coalesces_missing_fields() -> None:
    record = generator.build_printing_record({"id": "abc", "set": "neo"})
    assert record["id"] == "abc"
    assert record["set"] == "NEO"
    assert record["color_identity"] == []
    assert record["colors"] == []
    assert record["games"] == []
    assert record["set_name"] == ""
    assert record["collector_number"] == ""
    assert record["image_uris"] == {}
    assert record["fixture_image_sources"] == {}
    assert record["full_art"] is False
    assert record["promo"] is False
    assert record["digital"] is False
