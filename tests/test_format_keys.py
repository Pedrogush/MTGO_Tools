"""Tests for the canonical archetype-cache format key helpers."""

from utils.format_keys import normalize_archetype_list_cache, normalize_format_key


def test_normalize_format_key_folds_case_and_whitespace():
    assert normalize_format_key("Modern") == "modern"
    assert normalize_format_key("  MODERN ") == "modern"
    assert normalize_format_key("") == ""


def test_normalize_leaves_an_already_canonical_mapping_untouched():
    data = {"modern": {"timestamp": 5.0, "items": [{"name": "Boros Energy", "href": "boros"}]}}

    assert normalize_archetype_list_cache(data) == data


def test_case_variant_keys_collapse_to_one_entry():
    data = {
        "Modern": {"timestamp": 10.0, "items": [{"name": "A", "href": "a"}]},
        "modern": {"timestamp": 5.0, "items": [{"name": "B", "href": "b"}]},
    }

    normalized = normalize_archetype_list_cache(data)

    assert list(normalized) == ["modern"]
    # The freshest entry's timestamp survives; its items lead.
    assert normalized["modern"]["timestamp"] == 10.0
    assert [item["name"] for item in normalized["modern"]["items"]] == ["A", "B"]


def test_archetypes_known_only_to_the_older_entry_are_kept():
    """Migration must not silently drop archetypes a user already had cached."""
    shared = {"name": "Boros Energy", "href": "modern-boros-energy"}
    mtgo_only = {"name": "Dimir Frog", "href": "modern-dimir-frog", "source": "mtgo"}
    data = {
        "Modern": {"timestamp": 10.0, "items": [shared]},
        "modern": {"timestamp": 5.0, "items": [shared, mtgo_only]},
    }

    normalized = normalize_archetype_list_cache(data)

    assert normalized["modern"]["items"] == [shared, mtgo_only]


def test_items_are_deduplicated_by_href_not_by_identity():
    """The same archetype under both keys is one archetype, not two."""
    data = {
        "Modern": {"timestamp": 10.0, "items": [{"name": "Boros Energy", "href": "Boros"}]},
        "modern": {"timestamp": 5.0, "items": [{"name": "Boros Energy", "href": "boros"}]},
    }

    normalized = normalize_archetype_list_cache(data)

    assert normalized["modern"]["items"] == [{"name": "Boros Energy", "href": "Boros"}]


def test_items_without_an_href_fall_back_to_the_name():
    data = {
        "Modern": {"timestamp": 10.0, "items": [{"name": "Boros Energy"}]},
        "modern": {"timestamp": 5.0, "items": [{"name": "boros energy"}, {"name": "Tron"}]},
    }

    normalized = normalize_archetype_list_cache(data)

    assert [item["name"] for item in normalized["modern"]["items"]] == ["Boros Energy", "Tron"]


def test_unrelated_formats_are_preserved_under_canonical_keys():
    data = {
        "Modern": {"timestamp": 10.0, "items": []},
        "legacy": {"timestamp": 1.0, "items": [{"name": "ANT", "href": "ant"}]},
        " Pauper ": {"timestamp": 2.0, "items": [{"name": "Affinity", "href": "affinity"}]},
    }

    normalized = normalize_archetype_list_cache(data)

    assert sorted(normalized) == ["legacy", "modern", "pauper"]
    assert normalized["pauper"]["items"][0]["href"] == "affinity"


def test_missing_timestamps_and_items_do_not_raise():
    data = {
        "Modern": {"items": [{"name": "A", "href": "a"}]},
        "modern": {"timestamp": 3.0},
    }

    normalized = normalize_archetype_list_cache(data)

    assert normalized["modern"]["timestamp"] == 3.0
    assert normalized["modern"]["items"] == [{"name": "A", "href": "a"}]


def test_non_mapping_input_degrades_to_an_empty_mapping():
    assert normalize_archetype_list_cache(None) == {}
    assert normalize_archetype_list_cache([{"name": "A"}]) == {}


def test_non_mapping_entries_are_passed_through():
    """A corrupt entry keeps failing the way it always did, under the new key."""
    normalized = normalize_archetype_list_cache({"Modern": "not-an-entry"})

    assert normalized == {"modern": "not-an-entry"}
