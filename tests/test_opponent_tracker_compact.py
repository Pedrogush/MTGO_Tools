"""Compact mode for the opponent tracker: the floating chip's face, start spot,
hover card and saved state.

The chip itself is a wx window (verified on screen); what is pinned here is what
decides what it is given.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from utils.mtgo_window import find_match_window_rect, is_match_title
from widgets.frames.identify_opponent.compact import (
    CHIP_LOCKED_KEY,
    CHIP_POSITION_KEY,
    COMPACT_MODE_KEY,
    HOVER_SECTION_LINE_LIMIT,
    PORTRAIT_GUESS_FRACTION,
    ChipState,
    archetype_initials,
    chip_face,
    hover_section,
    hover_sections,
    initial_chip_position,
    popup_position,
)
from widgets.frames.identify_opponent.handlers import persistence as persistence_module

DISPLAY = (0, 0, 1920, 1040)
CHIP = (76, 32)


class TestChipFace:
    @pytest.mark.parametrize(
        ("archetype", "initials"),
        [
            ("Gruul Basking Broodscale", "GBB"),
            ("Boros Energy", "BE"),
            ("Burn", "BUR"),
            ("Four-Color Omnath Control", "FCO"),
            ("Goryo's Vengeance", "GV"),
        ],
    )
    def test_initials(self, archetype: str, initials: str) -> None:
        assert archetype_initials(archetype) == initials

    def test_no_opponent_is_idle(self) -> None:
        face = chip_face("", {})
        assert face.state == ChipState.IDLE

    def test_opponent_without_decks_is_unknown(self) -> None:
        face = chip_face("connormc02", {"Modern": "Unknown"})
        assert (face.label, face.state) == ("?", ChipState.UNKNOWN)

    def test_known_archetype_uses_the_first_known_format_like_the_radar(self) -> None:
        face = chip_face("connormc02", {"Modern": "Boros Energy", "Legacy": "Dimir Tempo"})
        assert (face.label, face.state) == ("BE", ChipState.KNOWN)


class TestInitialChipPosition:
    def test_a_saved_spot_wins(self) -> None:
        pos = initial_chip_position(
            chip_size=CHIP,
            display_area=DISPLAY,
            saved=[500, 300],
            match_window=(100, 100, 1000, 700),
        )
        assert pos == (500, 300)

    def test_without_a_saved_spot_it_guesses_under_the_portrait(self) -> None:
        pos = initial_chip_position(
            chip_size=CHIP, display_area=DISPLAY, match_window=(100, 50, 1000, 700)
        )
        fx, fy = PORTRAIT_GUESS_FRACTION
        assert pos == (100 + round(1000 * fx), 50 + round(700 * fy))

    def test_without_mtgo_it_starts_at_the_tracker(self) -> None:
        pos = initial_chip_position(
            chip_size=CHIP, display_area=DISPLAY, fallback_anchor=(640, 120, 740, 600)
        )
        assert pos == (640, 120)

    @pytest.mark.parametrize("saved", ["500,300", [1], ["a", "b"], None])
    def test_a_malformed_saved_spot_is_ignored(self, saved: object) -> None:
        pos = initial_chip_position(
            chip_size=CHIP, display_area=DISPLAY, saved=saved, fallback_anchor=(10, 20, 1, 1)
        )
        assert pos == (10, 20)

    def test_a_spot_on_a_missing_monitor_is_pulled_back_on_screen(self) -> None:
        pos = initial_chip_position(chip_size=CHIP, display_area=DISPLAY, saved=[3000, -200])
        assert pos == (1920 - CHIP[0], 0)


class TestPopupPosition:
    def test_opens_to_the_right_of_the_chip(self) -> None:
        assert popup_position((100, 200, 76, 32), (300, 400), DISPLAY, gap=4) == (180, 200)

    def test_flips_left_at_the_right_edge(self) -> None:
        assert popup_position((1800, 200, 76, 32), (300, 400), DISPLAY, gap=4) == (1496, 200)

    def test_stays_above_the_bottom_edge(self) -> None:
        assert popup_position((100, 900, 76, 32), (300, 400), DISPLAY, gap=4) == (180, 640)


class TestHoverCard:
    def test_long_lists_are_cut_with_a_count(self) -> None:
        lines = [f"{i}x Card" for i in range(HOVER_SECTION_LINE_LIMIT + 5)]

        section = hover_section("Radar: Burn", lines)

        assert len(section.lines) == HOVER_SECTION_LINE_LIMIT + 1
        assert section.lines[-1] == "… +5 more"

    def test_trailing_blank_lines_are_dropped(self) -> None:
        assert hover_section("Guide", ["a", "", " "]).lines == ("a",)

    def test_empty_sections_are_left_out(self) -> None:
        built = hover_sections([("Radar: —", []), ("Guide: Burn", ["+2 Kor Firewalker"])])
        assert [s.heading for s in built] == ["Guide: Burn"]


class TestMatchWindowTitle:
    @pytest.mark.parametrize(
        ("title", "opponent", "expected"),
        [
            ("Match: me vs. connormc02", None, True),
            ("Match: me vs. connormc02", "connormc02", True),
            ("Match: me vs. connormc02", "someone", False),
            ("Magic: The Gathering Online", None, False),
            ("Trailing vs.", None, False),
        ],
    )
    def test_title_rule_matches_the_detector(
        self, title: str, opponent: str | None, expected: bool
    ) -> None:
        assert is_match_title(title, opponent) is expected

    @pytest.mark.skipif(__import__("os").name == "nt", reason="off Windows the lookup is a no-op")
    def test_lookup_answers_none_off_windows(self) -> None:
        assert find_match_window_rect() is None


class _ConfigHost(persistence_module.PersistenceMixin):
    def __init__(self) -> None:
        self._saved_position: list[int] | None = None
        self._collapsed_sections: set[str] = set()
        self._compact_mode = False
        self._chip_position: list[int] | None = None
        self._chip_locked = True

    def GetPosition(self) -> tuple[int, int]:
        return (0, 0)


class TestCompactStatePersists:
    def test_compact_mode_chip_spot_and_padlock_survive_a_restart(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "deck_monitor_config.json"
        monkeypatch.setattr(persistence_module, "DECK_MONITOR_CONFIG_FILE", config_file)

        before = _ConfigHost()
        before._compact_mode = True
        before._chip_position = [480, 384]
        before._chip_locked = False
        before._save_config()

        after = _ConfigHost()
        after._load_config()

        assert after._compact_mode is True
        assert after._chip_position == [480, 384]
        assert after._chip_locked is False

    def test_an_old_config_starts_full_size_with_the_chip_locked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "deck_monitor_config.json"
        config_file.write_text(json.dumps({"screen_pos": [1, 2]}), encoding="utf-8")
        monkeypatch.setattr(persistence_module, "DECK_MONITOR_CONFIG_FILE", config_file)

        host = _ConfigHost()
        host._load_config()

        assert host._compact_mode is False
        assert host._chip_position is None
        assert host._chip_locked is True

    def test_saved_keys_are_the_documented_ones(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "deck_monitor_config.json"
        monkeypatch.setattr(persistence_module, "DECK_MONITOR_CONFIG_FILE", config_file)

        _ConfigHost()._save_config()

        saved = json.loads(config_file.read_text(encoding="utf-8"))
        assert {COMPACT_MODE_KEY, CHIP_POSITION_KEY, CHIP_LOCKED_KEY} <= saved.keys()
