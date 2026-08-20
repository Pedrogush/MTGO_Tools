"""Regression tests for duplicate art entries in the card inspector's pager.

Scryfall publishes the *foil run* of a printing as a second card object with
its own id and a ``★``-suffixed collector number, but the same
``illustration_id`` and the same frame. The inspector pages through **art**, so
those pairs read as "the same art listed twice" — e.g. Lightning Bolt's Secret
Lair 1638 / 1638★.

The fixture holds the real bulk-data records (trimmed to the fields the index
consumes) for three cards with many printings, so this is deterministic in CI
with no network call:

* Lightning Bolt — the reported card, one collapsing SLD pair;
* Arcane Signet — six collapsing pairs across SLD and 40K;
* Shivan Dragon — one collapsing pair plus five ``★``/``†`` pairs that must
  *not* collapse (the core-set foils are black-bordered while their nonfoil
  siblings are white-bordered, so they really do look different).
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from services.image_service.printing_index import build_printing_index

FIXTURE = Path(__file__).parent / "fixtures" / "printing_index" / "finish_variants.json"

# Lightning Bolt's Secret Lair 1638, nonfoil and rainbow foil.
SLD_1638_NONFOIL = "4f43c378-9e6a-4ece-9c24-5dc08c977746"
SLD_1638_FOIL = "54199d7c-02f8-4ff0-9e43-e7bf66ef9715"


@pytest.fixture(scope="module")
def bulk_cards() -> list[dict[str, Any]]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def records_by_id(bulk_cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {card["id"]: card for card in bulk_cards}


def _ids(by_name: dict[str, list[dict[str, Any]]], name: str) -> list[str]:
    return [entry["id"] for entry in by_name[name]]


def test_fixture_pair_differs_only_by_finish(records_by_id: dict[str, dict[str, Any]]) -> None:
    """The evidence behind the fix: one card, one art, two finishes."""
    nonfoil = records_by_id[SLD_1638_NONFOIL]
    foil = records_by_id[SLD_1638_FOIL]

    assert nonfoil["finishes"] == ["nonfoil"]
    assert foil["finishes"] == ["foil"]
    assert foil["collector_number"] == nonfoil["collector_number"] + "★"
    for field in ("set", "illustration_id", "frame", "frame_effects", "border_color", "artist"):
        assert foil[field] == nonfoil[field], field


def test_lightning_bolt_lists_each_art_once(
    bulk_cards: list[dict[str, Any]], records_by_id: dict[str, dict[str, Any]]
) -> None:
    by_name, _stats = build_printing_index(bulk_cards)
    ids = _ids(by_name, "lightning bolt")

    # 71 bulk records; SLD 1638★ only repeats SLD 1638's art.
    assert len(ids) == 70
    assert SLD_1638_NONFOIL in ids
    assert SLD_1638_FOIL not in ids

    # No surviving pair is the same set + collector number + art + frame.
    seen: set[tuple[str, ...]] = set()
    for uuid in ids:
        card = records_by_id[uuid]
        identity = (
            card["set"],
            card["collector_number"].replace("★", "").replace("†", ""),
            card.get("illustration_id") or "",
            card.get("frame") or "",
            ",".join(card.get("frame_effects") or ()),
            card.get("border_color") or "",
        )
        assert identity not in seen, f"duplicate art entry: {identity}"
        seen.add(identity)


def test_arcane_signet_collapses_every_finish_pair(bulk_cards: list[dict[str, Any]]) -> None:
    by_name, _stats = build_printing_index(bulk_cards)
    ids = _ids(by_name, "arcane signet")

    # 89 bulk records, six of them foil-only repeats (SLD 820/1492/1641,
    # 40K 227/228/229).
    assert len(ids) == 83
    assert not [uuid for uuid in ids if uuid is None]


def test_border_variants_are_not_collapsed(
    bulk_cards: list[dict[str, Any]], records_by_id: dict[str, dict[str, Any]]
) -> None:
    """A foil that is *also* re-bordered is a different-looking card: keep it."""
    by_name, _stats = build_printing_index(bulk_cards)
    ids = _ids(by_name, "shivan dragon")

    # 52 records, only the 10E pair (black-bordered both ways) collapses.
    assert len(ids) == 51

    kept = {(records_by_id[uuid]["set"], records_by_id[uuid]["collector_number"]) for uuid in ids}
    # White-bordered nonfoil + black-bordered foil survive as separate entries.
    for set_code, collector in (
        ("9ed", "219"),
        ("9ed", "219★"),
        ("7ed", "218"),
        ("7ed", "218★"),
        ("5ed", "267"),
        ("5ed", "267†"),
    ):
        assert (set_code, collector) in kept


def test_total_printings_stat_excludes_collapsed_variants(
    bulk_cards: list[dict[str, Any]],
) -> None:
    by_name, stats = build_printing_index(bulk_cards)

    assert stats["total_printings"] == len(bulk_cards) - 8  # 1 + 6 + 1
    assert stats["total_printings"] == sum(
        len(by_name[name]) for name in ("lightning bolt", "arcane signet", "shivan dragon")
    )


def test_art_order_is_stable_regardless_of_bulk_order(bulk_cards: list[dict[str, Any]]) -> None:
    """The pager is navigated by index, so the list must not shuffle per run."""
    baseline, _stats = build_printing_index(bulk_cards)

    for seed in (1, 2, 3):
        shuffled = list(bulk_cards)
        random.Random(seed).shuffle(shuffled)
        by_name, _stats = build_printing_index(shuffled)
        for name in ("lightning bolt", "arcane signet", "shivan dragon"):
            assert _ids(by_name, name) == _ids(baseline, name), f"{name} reordered (seed {seed})"
