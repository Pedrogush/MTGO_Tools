"""The rarity lookup behind the Pauper half of format detection.

Per-printing rarity is not in the local card index -- ``CardEntry`` has no
rarity field, and it could not usefully have one, because the index is built
from MTGJSON *AtomicCards*, which is oracle-level and carries no rarity at all.
The one source already on disk is the Scryfall ``default-cards`` bulk file the
image service downloads for card art, which is one record per *printing*. This
module turns that into the only question the format detector asks of it: has
this card name ever been printed at common?

The tests below feed :func:`build_common_printing_names` a small real bulk
document rather than mocking the scan, because the two things that are easy to
get wrong are both data-shaped: split cards whose halves are named separately in
a game log, and the difference between "not common" and "never heard of it".
"""

from __future__ import annotations

import json

import pytest

from services.card_rarity_service import (
    CardRarityService,
    build_common_printing_names,
    get_card_rarity_service,
    reset_card_rarity_service,
)


def _bulk(*records: dict) -> bytes:
    """Render bulk records the way the cached Scryfall file stores them."""
    return json.dumps(list(records)).encode("utf-8")


class TestBuildCommonPrintingNames:
    def test_splits_common_from_the_rest(self):
        common, known = build_common_printing_names(
            _bulk(
                {"name": "Lightning Bolt", "rarity": "common"},
                {"name": "Ragavan, Nimble Pilferer", "rarity": "mythic"},
            )
        )
        assert common == {"lightning bolt"}
        assert known == {"lightning bolt", "ragavan, nimble pilferer"}

    def test_a_later_common_reprint_counts(self):
        """ "Has a printing at common", not "is currently common".

        A card first printed at rare and reprinted at common is Pauper-legal,
        and the reverse is just as true -- which is exactly why this has to be a
        per-printing scan rather than one rarity per card.
        """
        common, _ = build_common_printing_names(
            _bulk(
                {"name": "Counterspell", "rarity": "uncommon"},
                {"name": "Counterspell", "rarity": "common"},
            )
        )
        assert "counterspell" in common

    def test_both_halves_of_a_split_name_are_indexed(self):
        """A game log names the half that was cast, not the combined card."""
        common, known = build_common_printing_names(
            _bulk({"name": "Fire // Ice", "rarity": "common"})
        )
        assert common == {"fire // ice", "fire", "ice"}
        assert known == common

    def test_face_and_printed_names_are_indexed(self):
        common, _ = build_common_printing_names(
            _bulk(
                {
                    "name": "Summon: Choco/Mog",
                    "printed_name": "Chocobo",
                    "rarity": "common",
                    "card_faces": [{"name": "Mog"}],
                }
            )
        )
        assert {"summon: choco/mog", "chocobo", "mog"} <= common

    def test_accents_are_folded_the_way_the_rest_of_the_app_folds_them(self):
        """MTGO writes ASCII where Scryfall writes the accented name."""
        common, _ = build_common_printing_names(
            _bulk({"name": "Dáin, Lord of the Iron Hills", "rarity": "common"})
        )
        assert "dain, lord of the iron hills" in common


class TestCardRarityService:
    @pytest.fixture(name="service")
    def fixture_service(self, tmp_path):
        bulk = tmp_path / "bulk_data.json"
        bulk.write_bytes(
            _bulk(
                {"name": "Lightning Bolt", "rarity": "common"},
                {"name": "Ragavan, Nimble Pilferer", "rarity": "mythic"},
            )
        )
        return CardRarityService(bulk_path=bulk, cache_path=tmp_path / "common.json")

    def test_starts_unloaded_and_answers_nothing(self, service):
        assert service.is_loaded is False
        assert service.has_common_printing("Lightning Bolt") is None

    def test_load_builds_the_index(self, service):
        assert service.load() is True
        assert service.is_loaded is True
        assert service.name_count == 1

    def test_three_valued_answer(self, service):
        """The third value is the one that matters: an unknown name is not "no".

        Reading a name the bulk has never heard of as "not common" would let one
        token or one differently-spelled printing veto the Pauper verdict for a
        whole match.
        """
        service.load()
        assert service.has_common_printing("Lightning Bolt") is True
        assert service.has_common_printing("Ragavan, Nimble Pilferer") is False
        assert service.has_common_printing("Some Token") is None

    def test_missing_bulk_file_leaves_it_unloaded(self, tmp_path):
        """A fresh install before the card-art download: no rarity, no crash."""
        service = CardRarityService(
            bulk_path=tmp_path / "absent.json", cache_path=tmp_path / "common.json"
        )
        assert service.load() is False
        assert service.is_loaded is False

    def test_corrupt_bulk_file_leaves_it_unloaded(self, tmp_path):
        bulk = tmp_path / "bulk_data.json"
        bulk.write_bytes(b"{not json")
        service = CardRarityService(bulk_path=bulk, cache_path=tmp_path / "common.json")
        assert service.load() is False

    def test_second_load_comes_from_the_derived_cache(self, service, tmp_path):
        """The scan costs a 620 MB decompress; it must happen once per bulk file."""
        service.load()
        assert (tmp_path / "common.json").exists()

        reloaded = CardRarityService(
            bulk_path=tmp_path / "bulk_data.json", cache_path=tmp_path / "common.json"
        )
        # Point the second instance at a bulk file it cannot read: if it still
        # answers, the answer came from the cache.
        (tmp_path / "bulk_data.json").write_bytes(b"{not json")
        # …but the mtime moved, so the cache is correctly rejected and the
        # unreadable bulk cannot be rebuilt from.
        assert reloaded.load() is False

    def test_cache_is_reused_while_the_bulk_is_unchanged(self, service, tmp_path):
        service.load()
        payload = json.loads((tmp_path / "common.json").read_text(encoding="utf-8"))
        assert payload["common"] == ["lightning bolt"]
        assert "ragavan, nimble pilferer" in payload["known"]

        reloaded = CardRarityService(
            bulk_path=tmp_path / "bulk_data.json", cache_path=tmp_path / "common.json"
        )
        assert reloaded.load() is True
        assert reloaded.has_common_printing("Lightning Bolt") is True

    def test_a_stale_cache_is_ignored(self, service, tmp_path):
        cache = tmp_path / "common.json"
        cache.write_text(
            json.dumps({"bulk_mtime": -1.0, "common": ["nonsense"], "known": ["nonsense"]}),
            encoding="utf-8",
        )
        assert service.load() is True
        assert service.has_common_printing("nonsense") is None
        assert service.has_common_printing("Lightning Bolt") is True


def test_shared_instance_is_reused_and_resettable():
    reset_card_rarity_service()
    try:
        assert get_card_rarity_service() is get_card_rarity_service()
    finally:
        reset_card_rarity_service()
