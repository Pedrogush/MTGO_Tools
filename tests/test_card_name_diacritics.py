"""Cards whose real name carries a diacritic, spelled in ASCII by MTGO.

MTGO deals you "Gloin the Mighty"; Scryfall and MTGJSON carry
"Glóin the Mighty // Easy Pickings". Every index in the app is keyed by
``name.lower()``, so before this fix those cards missed everywhere at once:

* the printing index had no entry, so the card inspector showed neither the
  art pager nor the edition picker (the reported symptom),
* the local bulk image index missed, so every hover went out to the API,
* the disk cache missed even after the file had been downloaded, so the queue
  logged "Assuming card image download failed for Gloin the Mighty" and
  downloaded it again, forever,
* and MTGJSON metadata missed, dropping the card from the inspector text and
  from the deck's curve and colour stats.

The fix keys every one of those indexes under the accent-folded name as well,
always as a fallback so a real card of that name still wins.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any


class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating attributes on demand."""

    def __getattr__(self, name: str) -> Any:  # noqa: D401 - simple stub
        value: Any = type(name, (), {})
        setattr(self, name, value)
        return value


def _install_wx_stub() -> None:
    """Install a ``wx`` stub only when the real module is unavailable."""
    try:
        import wx  # noqa: F401
    except Exception:
        sys.modules["wx"] = _WxStub("wx")


_install_wx_stub()

from services import image_service as card_images  # noqa: E402
from services.image_service import schemas as card_images_schemas  # noqa: E402
from services.image_service.batch_resolver import (  # noqa: E402
    _build_card_index,
    _Entry,
    _key,
    _match_entry,
)
from services.image_service.downloader import BulkImageDownloader  # noqa: E402
from utils.card_names import fold_card_name  # noqa: E402

# The card from the report. An adventure, so its Scryfall name is the combined
# "Front // Back" form and the accent sits in the front face's name.
SCRYFALL_NAME = "Glóin the Mighty // Easy Pickings"
FRONT_FACE = "Glóin the Mighty"
MTGO_NAME = "Gloin the Mighty"


def _hobbit_record(**overrides: Any) -> dict[str, Any]:
    """The shape of the Scryfall record for the The Hobbit printing."""
    record = {
        "name": SCRYFALL_NAME,
        "id": "uuid-hob-99",
        "set": "hob",
        "set_name": "The Hobbit",
        "collector_number": "99",
        "released_at": "2026-08-14",
        "image_uris": {"normal": "https://cards.example/hob-99.jpg"},
        "card_faces": [{"name": FRONT_FACE}, {"name": "Easy Pickings"}],
    }
    record.update(overrides)
    return record


# ---------------------------------------------------------------------------
# fold_card_name
# ---------------------------------------------------------------------------


def test_fold_card_name_folds_the_spellings_that_actually_differ():
    """Only information Scryfall itself ignores when matching a name."""
    assert fold_card_name("Glóin the Mighty") == "gloin the mighty"
    assert fold_card_name("Dáin, Lord of the Iron Hills") == "dain, lord of the iron hills"
    assert fold_card_name("Lórien Revealed") == "lorien revealed"
    # Typographic punctuation MTGO and Scryfall disagree on.
    assert fold_card_name("Ajani’s Pridemate") == fold_card_name("Ajani's Pridemate")
    assert fold_card_name("Boom — Bust") == fold_card_name("Boom - Bust")
    # Ligatures NFKD leaves alone because they are distinct letters.
    assert fold_card_name("Æther Vial") == "aether vial"
    # Collapsed whitespace, and an empty key for empty input.
    assert fold_card_name("  Fire   //  Ice ") == "fire // ice"
    assert fold_card_name("") == ""


# ---------------------------------------------------------------------------
# Printing index — the reported symptom
# ---------------------------------------------------------------------------


def _printing_index(tmp_path, monkeypatch, records):
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bulk_path = cache_dir / "bulk_data.json"
    bulk_path.write_text(json.dumps(records), encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)
    monkeypatch.setattr(
        card_images_schemas, "PRINTING_INDEX_CACHE", cache_dir / "printings.json", raising=False
    )
    return card_images.ensure_printing_index_cache(force=True)["data"]


def test_printing_index_lists_printings_for_the_ascii_name(tmp_path, monkeypatch):
    """No entry here is exactly why the inspector had no arrows and no editions.

    The card inspector reads its printings straight out of this index, keyed by
    ``card_name.lower()``. A miss leaves ``inspector_printings`` empty, and the
    panel then hides both the art pager and the edition picker.
    """
    data = _printing_index(tmp_path, monkeypatch, [_hobbit_record()])

    assert [entry["id"] for entry in data[MTGO_NAME.lower()]] == ["uuid-hob-99"]
    # The accented spellings keep working, combined and per-face.
    assert [entry["id"] for entry in data[SCRYFALL_NAME.lower()]] == ["uuid-hob-99"]
    assert [entry["id"] for entry in data[FRONT_FACE.lower()]] == ["uuid-hob-99"]


def test_folded_alias_never_shadows_a_real_card_of_that_name(tmp_path, monkeypatch):
    """A card genuinely named the folded spelling keeps its own printings."""
    real_card = {
        "name": MTGO_NAME,
        "id": "uuid-real",
        "set": "xxx",
        "set_name": "Somewhere",
        "collector_number": "1",
        "released_at": "2020-01-01",
    }
    data = _printing_index(tmp_path, monkeypatch, [_hobbit_record(), real_card])

    assert [entry["id"] for entry in data[MTGO_NAME.lower()]] == ["uuid-real"]


def test_printed_name_aliases_are_folded_too(tmp_path, monkeypatch):
    """The two alias kinds compose: a printed name may itself carry an accent."""
    record = _hobbit_record(
        name="Superior Spider-Man",
        printed_name="Kavaéro, Mind-Bitten",
        card_faces=None,
        id="uuid-om1-140",
        set="om1",
    )
    data = _printing_index(tmp_path, monkeypatch, [record])

    assert [entry["id"] for entry in data["kavaero, mind-bitten"]] == ["uuid-om1-140"]


# ---------------------------------------------------------------------------
# Local bulk image index
# ---------------------------------------------------------------------------


def test_local_bulk_index_resolves_the_ascii_name(tmp_path, monkeypatch):
    """The steady-state hover path must resolve without going out to the API."""
    cache_dir = tmp_path / "card_images"
    cache_dir.mkdir(parents=True, exist_ok=True)
    bulk_path = cache_dir / "bulk_data.json"
    bulk_path.write_text(json.dumps([_hobbit_record()]), encoding="utf-8")

    monkeypatch.setattr(card_images_schemas, "IMAGE_CACHE_DIR", cache_dir, raising=False)
    monkeypatch.setattr(card_images_schemas, "BULK_DATA_CACHE", bulk_path, raising=False)

    cache = card_images.CardImageCache(cache_dir=cache_dir, db_path=cache_dir / "images.db")
    downloader = BulkImageDownloader(cache)

    resolved = downloader._resolve_card_locally(MTGO_NAME)

    assert resolved is not None
    assert resolved.id == "uuid-hob-99"


# ---------------------------------------------------------------------------
# Batched /cards/collection resolution
# ---------------------------------------------------------------------------


def test_batch_index_matches_the_ascii_name_against_the_accented_answer():
    """Scryfall resolves the ASCII name but answers under the accented one.

    Without the folded key ``_match_entry`` missed on the exact name and the
    card was reported as "not found" — a permanent failure the queue never
    retries.
    """
    index = _build_card_index([_hobbit_record()])

    assert _match_entry(_Entry(MTGO_NAME, None, None), index)["id"] == "uuid-hob-99"
    assert _match_entry(_Entry(FRONT_FACE, None, None), index)["id"] == "uuid-hob-99"


def test_batch_index_prefers_an_exact_name_over_another_cards_folded_form():
    """Folded keys are a fallback; a real card of that name still wins."""
    real_card = _hobbit_record(name=MTGO_NAME, id="uuid-real", card_faces=None)
    index = _build_card_index([_hobbit_record(), real_card])

    assert _match_entry(_Entry(MTGO_NAME, None, None), index)["id"] == "uuid-real"


def test_batch_window_coalesces_both_spellings_into_one_lookup():
    """Otherwise one window fires two lookups for the same card."""
    assert _key(MTGO_NAME, None, None) == _key(FRONT_FACE, None, None)
    assert _key(MTGO_NAME, "HOB", None) == _key(FRONT_FACE, "hob", None)
    # A uuid is already exact and is keyed by identity, not by name.
    assert _key(MTGO_NAME, None, "uuid-hob-99") == "id:uuid-hob-99"


# ---------------------------------------------------------------------------
# Disk cache — the "Assuming card image download failed" loop
# ---------------------------------------------------------------------------


def _cache_with_hobbit_image(tmp_path):
    cache = card_images.CardImageCache(
        cache_dir=tmp_path / "cache", db_path=tmp_path / "cache" / "images.db"
    )
    image_file = cache.cache_dir / "normal" / "uuid-hob-99.jpg"
    image_file.parent.mkdir(parents=True, exist_ok=True)
    image_file.write_bytes(b"fake")
    cache.add_image(
        uuid="uuid-hob-99",
        name=SCRYFALL_NAME,
        set_code="hob",
        collector_number="99",
        image_size="normal",
        file_path=image_file,
    )
    cache._path_cache.clear()
    return cache, image_file


def test_cache_lookup_by_ascii_name_finds_the_downloaded_file(tmp_path):
    """The download queue's own "did that work?" check, which used to say no.

    The image lands under the Scryfall name; the queue then asks for it under
    the MTGO name, and on a miss logs "Assuming card image download failed" and
    hands the request back to be downloaded again on the next pass.
    """
    cache, image_file = _cache_with_hobbit_image(tmp_path)

    assert cache.get_image_path(MTGO_NAME, "normal") == image_file
    # Both accented spellings keep working, combined and front-face only.
    assert cache.get_image_path(SCRYFALL_NAME, "normal") == image_file
    assert cache.get_image_path(FRONT_FACE, "normal") == image_file


def test_cache_printing_lookup_by_ascii_name(tmp_path):
    """The set-qualified check the queue uses once a printing is pinned."""
    cache, image_file = _cache_with_hobbit_image(tmp_path)

    assert (
        cache.get_image_path_for_printing(MTGO_NAME, "HOB", "normal", collector_number="99")
        == image_file
    )
    # Folding widens the name match only. The printing pin still holds.
    assert (
        cache.get_image_path_for_printing(MTGO_NAME, "HOB", "normal", collector_number="227")
        is None
    )
    assert cache.get_image_path_for_printing(MTGO_NAME, "LTR", "normal") is None
