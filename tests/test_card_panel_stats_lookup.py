"""Unit tests for stats-name resolution used by the Card panel."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from widgets.panels.card_panel.properties import (
    CardPanelPropertiesMixin,
    _find_card_frequency,
    _stats_lookup_names,
)


@dataclass
class _Freq:
    card_name: str
    total_copies: int = 1


def _mixin(**state: object) -> CardPanelPropertiesMixin:
    """Build a bare mixin instance with the ``self`` state its methods read.

    The mixin defines no ``__init__`` and mutates no UI, so a plain instance
    with the relevant ``_current_*`` attributes is sufficient to exercise its
    pure helpers without constructing the wx-backed panel.
    """
    instance = CardPanelPropertiesMixin()
    for name, value in state.items():
        setattr(instance, name, value)
    return instance


def test_stats_lookup_names_prefers_front_face_for_dfc() -> None:
    assert _stats_lookup_names("Ajani, Nacatl Pariah // Ajani, Nacatl Avenger") == [
        "Ajani, Nacatl Pariah",
        "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger",
    ]


def test_stats_lookup_names_passes_through_simple_card() -> None:
    assert _stats_lookup_names("Lightning Bolt") == ["Lightning Bolt"]


def test_find_card_frequency_matches_front_face_when_data_uses_short_name() -> None:
    cards = [_Freq(card_name="Ajani, Nacatl Pariah", total_copies=4)]
    found = _find_card_frequency(cards, "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger")
    assert found is not None
    assert found.total_copies == 4


def test_find_card_frequency_matches_full_dfc_name_when_data_uses_canonical() -> None:
    cards = [_Freq(card_name="Fire // Ice", total_copies=2)]
    found = _find_card_frequency(cards, "Fire // Ice")
    assert found is not None
    assert found.total_copies == 2


def test_find_card_frequency_is_case_insensitive_for_simple_card() -> None:
    cards = [_Freq(card_name="lightning bolt", total_copies=4)]
    found = _find_card_frequency(cards, "Lightning Bolt")
    assert found is not None
    assert found.total_copies == 4


def test_find_card_frequency_is_case_insensitive_for_dfc_front_face() -> None:
    cards = [_Freq(card_name="AJANI, NACATL PARIAH", total_copies=3)]
    found = _find_card_frequency(cards, "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger")
    assert found is not None
    assert found.total_copies == 3


def test_find_card_frequency_returns_none_when_no_match() -> None:
    cards = [_Freq(card_name="Lightning Bolt")]
    assert _find_card_frequency(cards, "Counterspell") is None


def test_find_card_frequency_returns_none_for_empty_list() -> None:
    assert _find_card_frequency([], "Lightning Bolt") is None


def test_stats_lookup_names_strips_surrounding_whitespace() -> None:
    assert _stats_lookup_names("  Lightning Bolt  ") == ["Lightning Bolt"]


def test_stats_lookup_names_returns_empty_for_empty_string() -> None:
    assert _stats_lookup_names("") == []


def test_stats_lookup_names_returns_empty_for_whitespace_only() -> None:
    assert _stats_lookup_names("   ") == []


def test_stats_lookup_names_skips_empty_front_face() -> None:
    # A ``//`` name whose front face is blank should not yield an empty
    # candidate; only the full (back-only) name is returned.
    assert _stats_lookup_names("// Ice") == ["// Ice"]


def test_find_card_frequency_ignores_entry_without_card_name() -> None:
    # Entries missing ``card_name`` fall back to the empty-string default and
    # never match a real lookup name.
    cards = [SimpleNamespace(total_copies=4)]
    assert _find_card_frequency(cards, "Lightning Bolt") is None


def test_find_card_frequency_matches_entry_with_empty_card_name() -> None:
    # The empty-string default must not spuriously match a blank candidate.
    cards = [SimpleNamespace(card_name="", total_copies=4)]
    assert _find_card_frequency(cards, "Lightning Bolt") is None


def test_format_number_handles_none() -> None:
    assert _mixin()._format_number(None) == "—"


def test_format_number_renders_integer_with_thousands_separator() -> None:
    assert _mixin()._format_number(1234) == "1,234"


def test_format_number_renders_whole_float_as_integer() -> None:
    assert _mixin()._format_number(1234.0) == "1,234"


def test_format_number_renders_fractional_float_with_two_decimals() -> None:
    assert _mixin()._format_number(1234.5) == "1,234.50"


def test_format_average_handles_none() -> None:
    assert _mixin()._format_average(None) == "—"


def test_format_average_renders_two_decimals() -> None:
    assert _mixin()._format_average(2.5) == "2.50"


def test_archetype_name_returns_none_when_no_archetype() -> None:
    assert _mixin(_current_archetype=None)._archetype_name() is None


def test_archetype_name_returns_none_when_name_missing() -> None:
    assert _mixin(_current_archetype={})._archetype_name() is None


def test_archetype_name_returns_name_when_present() -> None:
    assert _mixin(_current_archetype={"name": "Burn"})._archetype_name() == "Burn"


def test_lookup_main_freq_returns_none_without_radar() -> None:
    assert _mixin(_current_radar=None)._lookup_main_freq("Lightning Bolt") is None


def test_lookup_side_freq_returns_none_without_radar() -> None:
    assert _mixin(_current_radar=None)._lookup_side_freq("Lightning Bolt") is None


def test_lookup_main_freq_resolves_front_face_from_radar() -> None:
    radar = SimpleNamespace(
        mainboard_cards=[_Freq(card_name="Ajani, Nacatl Pariah", total_copies=4)],
        sideboard_cards=[],
    )
    found = _mixin(_current_radar=radar)._lookup_main_freq(
        "Ajani, Nacatl Pariah // Ajani, Nacatl Avenger"
    )
    assert found is not None
    assert found.total_copies == 4


def test_lookup_side_freq_resolves_from_radar() -> None:
    radar = SimpleNamespace(
        mainboard_cards=[],
        sideboard_cards=[_Freq(card_name="Lightning Bolt", total_copies=2)],
    )
    found = _mixin(_current_radar=radar)._lookup_side_freq("Lightning Bolt")
    assert found is not None
    assert found.total_copies == 2
