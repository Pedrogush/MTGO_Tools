from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

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
    # The threshold is strictly greater-than 150: a gray with luminance exactly
    # 150 stays on the light-text branch, and one tick brighter flips to dark.
    assert generator.contrast_color((150, 150, 150)) == (245, 245, 240)
    assert generator.contrast_color((151, 151, 151)) == (20, 22, 25)


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


def test_build_printing_record_preserves_populated_fields() -> None:
    record = generator.build_printing_record(
        {
            "id": "abc",
            "oracle_id": "oid",
            "name": "Apothecary White",
            "mana_cost": "{W}",
            "type_line": "Creature",
            "colors": ["W"],
            "color_identity": ["W"],
            "set": "neo",
            "set_name": "Kamigawa",
            "collector_number": "5",
            "released_at": "2022-02-18",
            "artist": "Artist",
            "rarity": "rare",
            "layout": "normal",
            "games": ["paper", "mtgo"],
            "full_art": True,
            "textless": True,
            "promo": True,
            "digital": True,
            "variation": True,
            "border_color": "black",
            "frame": "2015",
            "image_uris": {"normal": "images/normal/x.jpg"},
            "fixture_image_sources": {"normal": "cache/card_images/normal/x.jpg"},
        }
    )
    assert record["oracle_id"] == "oid"
    assert record["mana_cost"] == "{W}"
    assert record["colors"] == ["W"]
    assert record["color_identity"] == ["W"]
    assert record["set"] == "NEO"
    assert record["set_name"] == "Kamigawa"
    assert record["collector_number"] == "5"
    assert record["released_at"] == "2022-02-18"
    assert record["games"] == ["paper", "mtgo"]
    assert record["full_art"] is True
    assert record["textless"] is True
    assert record["promo"] is True
    assert record["digital"] is True
    assert record["variation"] is True
    assert record["image_uris"] == {"normal": "images/normal/x.jpg"}
    assert record["fixture_image_sources"] == {"normal": "cache/card_images/normal/x.jpg"}


def _color_identity_for(name: str) -> list[str]:
    for group_name, group in generator.TARGETS.items():
        for identity, card_name in group.items():
            if card_name != name:
                continue
            if group_name in {"colorless", "nonbasic_land"}:
                return []
            return [c for c in COLOR_ORDER if c in identity]
    raise AssertionError(f"unknown target name: {name}")


def _type_line_for(name: str) -> str:
    for group_name, group in generator.TARGETS.items():
        for card_name in group.values():
            if card_name == name:
                return "Land" if group_name == "nonbasic_land" else "Legendary Creature"
    raise AssertionError(f"unknown target name: {name}")


def _write_bulk_cache(source: Path) -> list[dict]:
    """Build a minimal JSONL bulk cache covering every TARGETS card name."""
    cards: list[dict] = []
    counter = 0
    for name in sorted(generator.wanted_names()):
        # Two printings per name so printing-count math and sorting are exercised.
        for index, released in enumerate(("2021-01-01", "2022-02-02")):
            counter += 1
            cards.append(
                {
                    "object": "card",
                    "lang": "en",
                    "id": f"id-{counter:04d}",
                    "oracle_id": f"oracle-{name}",
                    "name": name,
                    "type_line": _type_line_for(name),
                    "color_identity": _color_identity_for(name),
                    "colors": _color_identity_for(name),
                    "set": f"s{counter % 7}",
                    "set_name": "Test Set",
                    "collector_number": str(counter),
                    "released_at": released,
                    "full_art": index == 0,
                    "image_uris": {
                        "small": "https://example.test/small.jpg",
                        "normal": "https://example.test/normal.jpg",
                    },
                }
            )

    # Add cards that must be filtered out by selected_printings().
    cards.append(
        {
            "object": "card",
            "lang": "ja",  # wrong language
            "id": "skip-lang",
            "name": "Apothecary White",
            "color_identity": ["W"],
            "image_uris": {"normal": "https://example.test/normal.jpg"},
        }
    )
    cards.append(
        {
            "object": "card",
            "lang": "en",
            "id": "skip-noimage",  # no normal image
            "name": "Apothecary White",
            "color_identity": ["W"],
            "image_uris": {},
        }
    )
    cards.append(
        {
            "object": "card",
            "lang": "en",
            "id": "skip-notwanted",  # not a target name
            "name": "Some Other Card",
            "color_identity": [],
            "image_uris": {"normal": "https://example.test/normal.jpg"},
        }
    )
    cards.append(
        {
            "object": "token",  # not a card object
            "lang": "en",
            "id": "skip-token",
            "name": "Apothecary White",
            "color_identity": ["W"],
            "image_uris": {"normal": "https://example.test/normal.jpg"},
        }
    )

    source.parent.mkdir(parents=True, exist_ok=True)
    with source.open("w", encoding="utf-8") as handle:
        handle.write("[\n")
        for i, card in enumerate(cards):
            suffix = "," if i < len(cards) - 1 else ""
            handle.write(json.dumps(card) + suffix + "\n")
        handle.write("]\n")
    return cards


def test_write_fixture_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Relocate the project root onto the temp surface so the real relative-path
    # rewriting (cached_image.relative_to(PROJECT_ROOT)) operates on tmp_path I/O.
    monkeypatch.setattr(generator, "PROJECT_ROOT", tmp_path)
    source = tmp_path / "cache" / "card_images" / "bulk_data.json"
    image_cache = tmp_path / "cache" / "card_images"
    output = tmp_path / "out"
    _write_bulk_cache(source)

    # Seed a real cached image for exactly one id+size so the copy branch runs
    # for it while every other size/printing falls through to a placeholder.
    cached_id = "id-0001"
    cached_size, cached_ext = generator.IMAGE_SPECS["small"]
    cached_dir = image_cache / "small"
    cached_dir.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", cached_size, (1, 2, 3)).save(cached_dir / f"{cached_id}.{cached_ext}")

    generator.write_fixture(source, image_cache, output)

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((output / "printings_index.json").read_text(encoding="utf-8"))
    cards = json.loads((output / "scryfall_cards.json").read_text(encoding="utf-8"))
    assert (output / "README.md").exists()

    target_count = len(generator.wanted_names())
    # Two printings per target name were written.
    assert manifest["printing_count"] == target_count * 2
    assert len(cards) == target_count * 2
    assert manifest["card_names"] == sorted(generator.wanted_names())

    # "Apothecary White" also has skip records sharing its name (wrong language,
    # missing image, and a non-card token object). selected_printings() must drop
    # all three and keep only the two valid English card printings.
    apothecary = index["data"]["apothecary white"]
    assert [p["id"] for p in apothecary] == ["id-0009", "id-0010"]
    surviving_ids = {p["id"] for printings in index["data"].values() for p in printings}
    assert {"skip-lang", "skip-noimage", "skip-notwanted", "skip-token"}.isdisjoint(surviving_ids)

    sizes = generator.IMAGE_SPECS
    assert manifest["image_file_count"] == manifest["printing_count"] * len(sizes)
    # Exactly one cached image existed, so exactly one copy happened.
    assert manifest["copied_cached_image_count"] == 1
    assert manifest["generated_placeholder_image_count"] == manifest["image_file_count"] - 1
    assert (
        manifest["copied_cached_image_count"] + manifest["generated_placeholder_image_count"]
        == manifest["image_file_count"]
    )
    # One full-art printing per name (the first of each pair).
    assert manifest["full_art_printing_count"] == target_count

    # The copied image's source points back into the cache; placeholders are tagged.
    copied = [
        source_name
        for printings in index["data"].values()
        for printing in printings
        for source_name in printing["fixture_image_sources"].values()
        if source_name != "generated_placeholder"
    ]
    assert copied == ["cache/card_images/small/id-0001.jpg"]

    # Every rewritten image path is relative and the file exists on disk.
    for printings in index["data"].values():
        for printing in printings:
            assert set(printing["fixture_image_sources"]) == set(printing["image_uris"])
            for image_path in printing["image_uris"].values():
                assert not image_path.startswith(("http://", "https://"))
                assert (output / image_path).exists()

    # Printings are sorted oldest-first by release date.
    sample = index["data"]["apothecary white"]
    assert [p["released_at"] for p in sample] == ["2021-01-01", "2022-02-02"]

    # source_image_uris preserves the original Scryfall URLs on the full records.
    for card in cards:
        assert card["source_image_uris"]["normal"].startswith("https://")
        for image_path in card["image_uris"].values():
            assert not image_path.startswith(("http://", "https://"))


def test_write_fixture_raises_when_source_missing(tmp_path: Path) -> None:
    image_cache = tmp_path / "cache"
    image_cache.mkdir()
    with pytest.raises(FileNotFoundError, match="Source bulk cache not found"):
        generator.write_fixture(tmp_path / "missing.json", image_cache, tmp_path / "out")


def test_write_fixture_raises_when_image_cache_missing(tmp_path: Path) -> None:
    source = tmp_path / "bulk_data.json"
    source.write_text("[]\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="Image cache not found"):
        generator.write_fixture(source, tmp_path / "no_cache", tmp_path / "out")


def test_selected_printings_raises_when_target_missing(tmp_path: Path) -> None:
    source = tmp_path / "bulk_data.json"
    # A valid card record, but not one of the required target names.
    source.write_text(
        json.dumps(
            {
                "object": "card",
                "lang": "en",
                "id": "x",
                "name": "Not A Target",
                "image_uris": {"normal": "https://example.test/n.jpg"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="Missing target cards"):
        generator.selected_printings(source)


def test_draw_placeholder_writes_jpg_and_png(tmp_path: Path) -> None:
    card = {
        "id": "abcdef123456",
        "name": "Some Very Long Card Name For Wrapping",
        "set": "neo",
        "collector_number": "12",
        "released_at": "2022-02-18",
        "color_identity": ["W", "U"],
        "full_art": True,
    }
    jpg_path = tmp_path / "out" / "art.jpg"
    png_path = tmp_path / "out" / "art.png"
    generator.draw_placeholder(card, "normal", (200, 280), jpg_path)
    generator.draw_placeholder(card, "png", (200, 280), png_path)

    with Image.open(jpg_path) as jpg:
        assert jpg.size == (200, 280)
        assert jpg.format == "JPEG"
    with Image.open(png_path) as png:
        assert png.size == (200, 280)
        assert png.format == "PNG"


def test_parse_args_returns_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_card_art_selection_fixture.py",
            "--source",
            "/tmp/bulk.json",
            "--image-cache",
            "/tmp/cache",
            "--output",
            "/tmp/out",
        ],
    )
    args = generator.parse_args()
    assert args.source == Path("/tmp/bulk.json")
    assert args.image_cache == Path("/tmp/cache")
    assert args.output == Path("/tmp/out")


def test_parse_args_defaults_to_module_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["generate_card_art_selection_fixture.py"])
    args = generator.parse_args()
    assert args.source == generator.DEFAULT_SOURCE
    assert args.image_cache == generator.DEFAULT_IMAGE_CACHE
    assert args.output == generator.DEFAULT_OUTPUT


def test_main_dispatches_parsed_args_to_write_fixture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Path] = {}

    def fake_write_fixture(source: Path, image_cache: Path, output: Path) -> None:
        captured["source"] = source
        captured["image_cache"] = image_cache
        captured["output"] = output

    monkeypatch.setattr(generator, "write_fixture", fake_write_fixture)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_card_art_selection_fixture.py",
            "--source",
            "/tmp/bulk.json",
            "--image-cache",
            "/tmp/cache",
            "--output",
            "/tmp/out",
        ],
    )
    generator.main()
    assert captured == {
        "source": Path("/tmp/bulk.json"),
        "image_cache": Path("/tmp/cache"),
        "output": Path("/tmp/out"),
    }


def test_iter_bulk_cards_skips_brackets_and_trailing_commas(tmp_path: Path) -> None:
    source = tmp_path / "bulk_data.json"
    source.write_text(
        '[\n{"id": "1"},\n{"id": "2"}\n]\n',
        encoding="utf-8",
    )
    records = list(generator.iter_bulk_cards(source))
    assert [r["id"] for r in records] == ["1", "2"]
