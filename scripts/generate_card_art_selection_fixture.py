"""Generate the offline card-art-selection fixture.

The fixture is intentionally built from the local Scryfall bulk cache, not the
network. It keeps complete card records for a fixed set of card names and
copies cached local images where available, and creates deterministic fallback
image files for variants that are not present in the local cache so backend
tests can exercise art-selection rules without HTTP.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = PROJECT_ROOT / "cache" / "card_images" / "bulk_data.json"
DEFAULT_IMAGE_CACHE = PROJECT_ROOT / "cache" / "card_images"
DEFAULT_OUTPUT = PROJECT_ROOT / "tests" / "fixtures" / "card_art_selection"

COLOR_ORDER = "WUBRG"

TARGETS: dict[str, dict[str, str]] = {
    "mono": {
        "W": "Apothecary White",
        "U": "Blind Phantasm",
        "B": "Mastermind Plum",
        "R": "Duelist's Flame",
        "G": "Emissary Green",
    },
    "dual": {
        "WU": 'Miles "Tails" Prower',
        "WB": "Killian, Decisive Mentor",
        "WR": "Amy Rose",
        "WG": "Black Panther, Wakandan King",
        "UB": "Doc Ock, Evil Inventor",
        "UR": "Iron Man, Titan of Innovation",
        "UG": "Aloy, Savior of Meridian",
        "BR": "Green Goblin, Nemesis",
        "BG": "Dina, Essence Brewer",
        "RG": "Toph, Greatest Earthbender",
    },
    "tri": {
        "WUB": "Aminatou, Veil Piercer",
        "WUR": "Captain America, First Avenger",
        "WUG": "Aang and Katara",
        "WBR": "Neriv, Crackling Vanguard",
        "WBG": "Betor, Ancestor's Voice",
        "WRG": "Yuma, Proud Protector",
        "UBR": "Dr. Eggman",
        "UBG": "Gonti, Canny Acquisitor",
        "URG": "Eshki, Temur's Roar",
        "BRG": "Auntie Ool, Cursewretch",
    },
    "quad": {
        "WUBR": "Yore-Tiller Nephilim",
        "WUBG": "Sol, Advocate Eternal",
        "WURG": "The Fourteenth Doctor",
        "WBRG": "Dune-Brood Nephilim",
        "UBRG": "Yidris, Maelstrom Wielder",
    },
    "five_color": {
        "WUBRG": "Ashling, the Limitless",
    },
    "colorless": {
        "C": "Big Mother Mouser",
    },
    "nonbasic_land": {
        "LAND": "Eden, Seat of the Sanctum",
    },
}

IMAGE_SPECS: dict[str, tuple[tuple[int, int], str]] = {
    "small": ((146, 204), "jpg"),
    "normal": ((488, 680), "jpg"),
    "large": ((672, 936), "jpg"),
    "png": ((745, 1040), "png"),
    "art_crop": ((626, 457), "jpg"),
    "border_crop": ((480, 680), "jpg"),
}

COLOR_SWATCHES: dict[str, tuple[int, int, int]] = {
    "W": (236, 226, 196),
    "U": (84, 145, 196),
    "B": (64, 56, 65),
    "R": (207, 91, 55),
    "G": (77, 147, 91),
    "C": (160, 160, 150),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--image-cache", type=Path, default=DEFAULT_IMAGE_CACHE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def iter_bulk_cards(path: Path):
    with path.open(encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line in {"[", "]"}:
                continue
            if line.endswith(","):
                line = line[:-1]
            yield json.loads(line)


def color_identity_key(card: dict[str, Any]) -> str:
    values = set(card.get("color_identity") or [])
    return "".join(color for color in COLOR_ORDER if color in values)


def wanted_names() -> set[str]:
    return {name for group in TARGETS.values() for name in group.values()}


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "card"


def selected_printings(source: Path) -> dict[str, list[dict[str, Any]]]:
    names = wanted_names()
    found: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in iter_bulk_cards(source):
        name = card.get("name")
        if name not in names:
            continue
        if card.get("object") != "card" or card.get("lang") != "en":
            continue
        if not card.get("image_uris", {}).get("normal"):
            continue
        local_card = dict(card)
        local_card["source_image_uris"] = dict(card.get("image_uris") or {})
        found[name].append(local_card)

    missing = sorted(names - set(found))
    if missing:
        raise RuntimeError(f"Missing target cards from source bulk cache: {missing}")

    for printings in found.values():
        printings.sort(key=lambda card: (card.get("released_at") or "", card.get("set") or ""))
    return dict(found)


def image_color(card: dict[str, Any]) -> tuple[int, int, int]:
    identity = color_identity_key(card) or "C"
    if len(identity) == 1:
        return COLOR_SWATCHES[identity]
    channels = [COLOR_SWATCHES[color] for color in identity]
    return tuple(sum(channel[i] for channel in channels) // len(channels) for i in range(3))


def contrast_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    luminance = 0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]
    return (20, 22, 25) if luminance > 150 else (245, 245, 240)


def wrapped_lines(text: str, *, max_chars: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def draw_placeholder(
    card: dict[str, Any], image_key: str, size: tuple[int, int], path: Path
) -> None:
    bg = image_color(card)
    fg = contrast_color(bg)
    image = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    margin = max(8, size[0] // 24)
    line_gap = max(3, size[1] // 90)
    max_chars = max(10, size[0] // 9)
    lines = [
        *wrapped_lines(card.get("name") or "Unknown", max_chars=max_chars),
        "",
        f"{(card.get('set') or '').upper()} #{card.get('collector_number') or ''}",
        f"{card.get('released_at') or ''}",
        f"CI {color_identity_key(card) or 'C'}",
        f"full_art={bool(card.get('full_art'))}",
        f"image={image_key}",
        f"id={card.get('id', '')[:8]}",
    ]
    y = margin
    for line in lines:
        draw.text((margin, y), line, fill=fg, font=font)
        y += 10 + line_gap
    draw.rectangle((margin, margin, size[0] - margin, size[1] - margin), outline=fg, width=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".jpg":
        image.save(path, quality=88)
    else:
        image.save(path)


def attach_local_images(
    card: dict[str, Any], output: Path, image_cache: Path
) -> tuple[dict[str, str], dict[str, str]]:
    image_uris: dict[str, str] = {}
    image_sources: dict[str, str] = {}
    slug = slugify(card.get("name") or "card")
    card_id = card["id"]
    for key, (size, ext) in IMAGE_SPECS.items():
        rel = Path("images") / key / f"{slug}-{card_id}.{ext}"
        destination = output / rel
        cached_image = image_cache / key / f"{card_id}.{ext}"
        if cached_image.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(cached_image, destination)
            image_sources[key] = cached_image.relative_to(PROJECT_ROOT).as_posix()
        else:
            draw_placeholder(card, key, size, destination)
            image_sources[key] = "generated_placeholder"
        image_uris[key] = rel.as_posix()
    card["image_uris"] = image_uris
    card["fixture_image_sources"] = image_sources
    return image_uris, image_sources


def build_printing_record(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": card.get("id"),
        "oracle_id": card.get("oracle_id"),
        "name": card.get("name"),
        "mana_cost": card.get("mana_cost"),
        "type_line": card.get("type_line"),
        "colors": card.get("colors") or [],
        "color_identity": card.get("color_identity") or [],
        "set": (card.get("set") or "").upper(),
        "set_name": card.get("set_name") or "",
        "collector_number": card.get("collector_number") or "",
        "released_at": card.get("released_at") or "",
        "artist": card.get("artist") or "",
        "rarity": card.get("rarity") or "",
        "layout": card.get("layout") or "",
        "games": card.get("games") or [],
        "full_art": bool(card.get("full_art")),
        "textless": bool(card.get("textless")),
        "promo": bool(card.get("promo")),
        "digital": bool(card.get("digital")),
        "variation": bool(card.get("variation")),
        "border_color": card.get("border_color") or "",
        "frame": card.get("frame") or "",
        "image_uris": card.get("image_uris") or {},
        "fixture_image_sources": card.get("fixture_image_sources") or {},
    }


def write_fixture(source: Path, image_cache: Path, output: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(f"Source bulk cache not found: {source}")
    if not image_cache.exists():
        raise FileNotFoundError(f"Image cache not found: {image_cache}")
    output.mkdir(parents=True, exist_ok=True)

    by_name = selected_printings(source)
    cards: list[dict[str, Any]] = []
    printings_by_name: dict[str, list[dict[str, Any]]] = {}
    copied_cached_image_count = 0
    generated_placeholder_image_count = 0

    for name in sorted(by_name):
        for card in by_name[name]:
            _, image_sources = attach_local_images(card, output, image_cache)
            copied_cached_image_count += sum(
                1
                for source_name in image_sources.values()
                if source_name != "generated_placeholder"
            )
            generated_placeholder_image_count += sum(
                1
                for source_name in image_sources.values()
                if source_name == "generated_placeholder"
            )
            cards.append(card)
        printings_by_name[name.lower()] = [build_printing_record(card) for card in by_name[name]]

    manifest = {
        "fixture": "card_art_selection",
        "generated_at": datetime.now(UTC).isoformat(),
        "source_bulk_cache": str(source),
        "source_image_cache": str(image_cache),
        "image_sizes": {
            key: {"width": size[0], "height": size[1], "extension": ext}
            for key, (size, ext) in IMAGE_SPECS.items()
        },
        "categories": TARGETS,
        "card_names": sorted(by_name),
        "printing_count": sum(len(printings) for printings in by_name.values()),
        "full_art_printing_count": sum(
            1 for printings in by_name.values() for card in printings if card.get("full_art")
        ),
        "image_file_count": copied_cached_image_count + generated_placeholder_image_count,
        "copied_cached_image_count": copied_cached_image_count,
        "generated_placeholder_image_count": generated_placeholder_image_count,
    }

    printings_index = {
        "version": 1,
        "generated_at": manifest["generated_at"],
        "categories": TARGETS,
        "data": printings_by_name,
    }

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "scryfall_cards.json").write_text(json.dumps(cards, indent=2), encoding="utf-8")
    (output / "printings_index.json").write_text(
        json.dumps(printings_index, indent=2), encoding="utf-8"
    )
    (output / "README.md").write_text(
        "# Card Art Selection Fixture\n\n"
        "Offline fixture for backend art-selection work. It contains one chosen card for each "
        "requested color-identity bucket, all Scryfall printings for those exact card names, "
        "cached local Scryfall images where available, and deterministic placeholder images "
        "for uncached variants.\n\n"
        "Files:\n"
        "- `manifest.json`: category-to-card mapping and fixture summary.\n"
        "- `scryfall_cards.json`: complete selected Scryfall card records with `image_uris` "
        "rewritten to relative fixture files and `source_image_uris` preserving the original "
        "Scryfall URLs.\n"
        "- `printings_index.json`: compact backend-friendly printings index, including "
        "`full_art`, treatment flags, collector numbers, and local image paths.\n"
        "- `images/`: local images for every printing and image size. The generator copies "
        "cached `small`, `normal`, `large`, and `png` files when present; `art_crop` and "
        "`border_crop` are deterministic placeholders unless those caches exist locally.\n\n"
        "Regenerate with `python scripts/generate_card_art_selection_fixture.py` after refreshing "
        "`cache/card_images/bulk_data.json`.\n",
        encoding="utf-8",
    )

    print(
        f"Wrote {len(by_name)} cards / {manifest['printing_count']} printings "
        f"to {output.relative_to(PROJECT_ROOT)}"
    )


def main() -> None:
    args = parse_args()
    write_fixture(args.source, args.image_cache, args.output)


if __name__ == "__main__":
    main()
