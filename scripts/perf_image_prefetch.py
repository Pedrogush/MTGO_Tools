#!/usr/bin/env python3
"""Headless perf harness for the deck image prefetch path (issue #951).

Reproduces what the UI does when a decklist loads — submits every card of a
deck to ``ImageService.prefetch_card_images`` at the selected-deck priority —
and measures how long it takes until every image is on disk. No wx required,
so iterations can run from a terminal against a cache cleared by
``scripts/clear_image_cache.py``.

Usage (from the repo root):
    ./.venv/Scripts/python.exe scripts/perf_image_prefetch.py [--deck FILE]
        [--keep-cache] [--timeout SECONDS]

By default the image cache is cleared first (bulk data kept) so every run
starts cold and numbers are comparable.
"""

from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# A real 75-card list (Legacy Dimir Reanimator flavored), 33 unique names —
# representative of what a deck load submits.
SAMPLE_DECK = """
4 Entomb
4 Reanimate
4 Brainstorm
4 Ponder
4 Force of Will
4 Daze
3 Grief
2 Troll of Khazad-dum
1 Archon of Cruelty
1 Griselbrand
1 Atraxa, Grand Unifier
2 Animate Dead
2 Thoughtseize
1 Personal Tutor
2 Barrowgoyf
1 Murktide Regent
2 Underground Sea
4 Polluted Delta
4 Flooded Strand
2 Misty Rainforest
3 Island
1 Swamp
1 Marsh Flats
2 Wasteland
1 Bloodstained Mire
Sideboard
2 Surgical Extraction
2 Flusterstorm
1 Hydroblast
2 Barrowgoyf
1 Sheoldred, the Apocalypse
2 Force of Negation
1 Fatal Push
2 Consign to Memory
1 Faerie Macabre
1 Serra's Emissary
""".strip()


def parse_deck(text: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("sideboard"):
            continue
        parts = line.split(" ", 1)
        if len(parts) != 2 or not parts[0].isdigit():
            continue
        name = parts[1].strip()
        if name.lower() not in seen:
            seen.add(name.lower())
            names.append(name)
    return names


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--deck", type=Path, help="decklist file (default: embedded 75-card list)")
    parser.add_argument(
        "--keep-cache", action="store_true", help="do not clear the image cache first"
    )
    parser.add_argument("--timeout", type=float, default=180.0, help="give up after this long")
    parser.add_argument(
        "--startup-gap",
        type=float,
        default=0.0,
        help="seconds between service creation and the deck load, like a real "
        "session (lets the eager bulk-index warm finish off the critical path)",
    )
    args = parser.parse_args()

    if not args.keep_cache:
        from scripts.clear_image_cache import clear_image_cache

        clear_image_cache()

    deck_text = args.deck.read_text(encoding="utf-8") if args.deck else SAMPLE_DECK
    names = parse_deck(deck_text)
    print(f"Deck: {len(names)} unique card names")

    from services.image_service import ImageService
    from services.image_service.downloader import get_cache
    from services.image_service.priorities import PRIORITY_SELECTED_DECK

    service = ImageService()
    cache = get_cache()
    if args.startup_gap:
        time.sleep(args.startup_gap)

    batch_done = threading.Event()
    batch_result: dict[str, list[str]] = {}

    def on_batch(source: str, enqueued: list[str], skipped: list[str]) -> None:
        batch_result["enqueued"] = enqueued
        batch_result["skipped"] = skipped
        batch_done.set()

    # t0 = the moment the deck "loads": what the UI's PERF line measures from.
    t0 = time.perf_counter()
    service.prefetch_card_images("deck", names, priority=PRIORITY_SELECTED_DECK, on_batch=on_batch)

    if not batch_done.wait(timeout=30.0):
        print("FAIL: prefetch batch never ran (30s)")
        service.shutdown()
        return 1

    enqueued = batch_result["enqueued"]
    skipped = batch_result["skipped"]
    batch_ms = (time.perf_counter() - t0) * 1000.0
    print(f"Batch submitted in {batch_ms:.0f} ms: {len(enqueued)} to download, "
          f"{len(skipped)} already local/queued")

    remaining = set(enqueued)
    completion_ms: list[float] = []
    while remaining:
        elapsed = time.perf_counter() - t0
        if elapsed > args.timeout:
            print(f"TIMEOUT after {elapsed:.1f}s with {len(remaining)} images missing:")
            for name in sorted(remaining):
                print(f"  - {name}")
            break
        done = {name for name in remaining if cache.get_image_path(name, "normal") is not None}
        for _ in done:
            completion_ms.append(elapsed * 1000.0)
        remaining -= done
        if not remaining:
            break
        time.sleep(0.1)

    service.shutdown()

    total_ms = (time.perf_counter() - t0) * 1000.0
    downloaded = len(enqueued) - len(remaining)
    print()
    print(f"RESULT | downloaded {downloaded}/{len(enqueued)} images")
    if completion_ms:
        completion_ms.sort()
        p = lambda q: completion_ms[min(len(completion_ms) - 1, int(q * len(completion_ms)))]  # noqa: E731
        print(f"RESULT | first image  {completion_ms[0]:>8.0f} ms")
        print(f"RESULT | 50% local    {p(0.50):>8.0f} ms")
        print(f"RESULT | 90% local    {p(0.90):>8.0f} ms")
        print(f"RESULT | all local    {completion_ms[-1]:>8.0f} ms")
    print(f"RESULT | wall total   {total_ms:>8.0f} ms")
    return 0 if not remaining else 1


if __name__ == "__main__":
    raise SystemExit(main())
