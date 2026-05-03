"""Unit tests for stats-name resolution used by the Card panel."""

from __future__ import annotations

from dataclasses import dataclass

from widgets.panels.card_panel.properties import _find_card_frequency, _stats_lookup_names


@dataclass
class _Freq:
    card_name: str
    total_copies: int = 1


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
