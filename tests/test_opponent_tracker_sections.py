"""Folding the opponent tracker's sections down to their headings.

The wx edge (Show/Hide, sizer proportions, the sash) is driven by the frame; what
is pinned here is the arithmetic and state that decide what it is given: where
the sash goes, which column keeps the spare width, which body a pane shows when
it is unfolded again, and that the folded set survives a restart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from widgets.frames.identify_opponent.handlers import persistence as persistence_module
from widgets.frames.identify_opponent.sections import (
    COLLAPSED_SECTIONS_KEY,
    SECTION_CALCULATOR,
    SECTION_GUIDE,
    SECTION_RADAR,
    column_proportions,
    left_sash_target,
    parse_collapsed_sections,
    serialize_collapsed_sections,
)
from widgets.panels.compact_radar_panel.handlers import CompactRadarHandlersMixin
from widgets.panels.compact_sideboard_panel.handlers import CompactSideboardHandlersMixin


def _sash(**overrides: object) -> int:
    args: dict = {
        "calc_collapsed": False,
        "radar_collapsed": False,
        "calc_height": 330,
        "radar_height": 40,
        "splitter_height": 500,
        "sash_size": 6,
    }
    args.update(overrides)
    return left_sash_target(**args)


class TestLeftSashTarget:
    def test_both_open_fits_the_calculator(self) -> None:
        assert _sash() == 330

    def test_folded_calculator_gives_the_radar_everything_below_its_title(self) -> None:
        assert _sash(calc_collapsed=True, calc_height=40) == 40

    def test_folded_radar_drops_the_sash_to_just_above_its_heading(self) -> None:
        assert _sash(radar_collapsed=True) == 500 - 40 - 6

    def test_folded_radar_never_cuts_the_calculator_off(self) -> None:
        assert _sash(radar_collapsed=True, splitter_height=300) == 330

    def test_both_folded_puts_the_radar_heading_under_the_calculator_title(self) -> None:
        assert _sash(calc_collapsed=True, radar_collapsed=True, calc_height=40) == 40


class TestColumnProportions:
    def test_nothing_folded_keeps_the_normal_split(self) -> None:
        assert column_proportions(set(), left_proportion=2, guide_proportion=1) == (2, 1)

    def test_folded_guide_gives_its_width_to_the_left_column(self) -> None:
        assert column_proportions({SECTION_GUIDE}, left_proportion=2, guide_proportion=1) == (2, 0)

    def test_left_column_only_gives_up_width_once_both_its_sections_fold(self) -> None:
        assert column_proportions({SECTION_CALCULATOR}, left_proportion=2, guide_proportion=1) == (
            2,
            1,
        )
        assert column_proportions(
            {SECTION_CALCULATOR, SECTION_RADAR}, left_proportion=2, guide_proportion=1
        ) == (0, 1)

    def test_everything_folded_keeps_the_normal_split(self) -> None:
        everything = {SECTION_CALCULATOR, SECTION_RADAR, SECTION_GUIDE}
        assert column_proportions(everything, left_proportion=2, guide_proportion=1) == (2, 1)


class TestCollapsedSectionsConfig:
    def test_round_trip_is_in_on_screen_order(self) -> None:
        saved = serialize_collapsed_sections({SECTION_GUIDE, SECTION_CALCULATOR})

        assert saved == [SECTION_CALCULATOR, SECTION_GUIDE]
        assert parse_collapsed_sections(saved) == {SECTION_CALCULATOR, SECTION_GUIDE}

    @pytest.mark.parametrize("raw", [None, "radar", {"radar": True}, 3])
    def test_a_value_that_is_not_a_list_folds_nothing(self, raw: object) -> None:
        assert parse_collapsed_sections(raw) == set()

    def test_unknown_names_are_dropped(self) -> None:
        assert parse_collapsed_sections(["radar", "notes", 7]) == {SECTION_RADAR}


class _ConfigHost(persistence_module.PersistenceMixin):
    """The persistence mixin, with the one wx call it makes answered directly."""

    def __init__(self) -> None:
        self._saved_position: list[int] | None = None
        self._collapsed_sections: set[str] = set()

    def GetPosition(self) -> tuple[int, int]:
        return (120, 80)


class TestCollapsedSectionsPersist:
    def test_folded_sections_survive_a_restart(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "deck_monitor_config.json"
        monkeypatch.setattr(persistence_module, "DECK_MONITOR_CONFIG_FILE", config_file)

        before = _ConfigHost()
        before._collapsed_sections = {SECTION_RADAR, SECTION_GUIDE}
        before._save_config()

        on_disk = json.loads(config_file.read_text(encoding="utf-8"))
        assert on_disk[COLLAPSED_SECTIONS_KEY] == [SECTION_RADAR, SECTION_GUIDE]
        assert on_disk["screen_pos"] == [120, 80]

        after = _ConfigHost()
        after._load_config()
        assert after._collapsed_sections == {SECTION_RADAR, SECTION_GUIDE}
        assert after._saved_position == [120, 80]

    def test_a_config_from_before_folding_existed_opens_everything(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        config_file = tmp_path / "deck_monitor_config.json"
        config_file.write_text(json.dumps({"screen_pos": [1, 2]}), encoding="utf-8")
        monkeypatch.setattr(persistence_module, "DECK_MONITOR_CONFIG_FILE", config_file)

        host = _ConfigHost()
        host._load_config()

        assert host._collapsed_sections == set()


class _Shown:
    def __init__(self) -> None:
        self.shown = True

    def Show(self, show: bool = True) -> None:
        self.shown = show

    def Hide(self) -> None:
        self.shown = False


class _Caret:
    def __init__(self) -> None:
        self.collapsed = False

    def set_collapsed(self, collapsed: bool) -> None:
        self.collapsed = collapsed


class _Label(_Shown):
    def SetLabel(self, text: str) -> None:
        self.label = text


class _EmptyState(_Shown):
    def set_message(self, message: str, hint: str | None = None) -> None:
        self.message = message


def _pane_body(host: object) -> None:
    host.status_label = _Label()  # type: ignore[attr-defined]
    host.card_list = _Shown()  # type: ignore[attr-defined]
    host.empty_state = _EmptyState()  # type: ignore[attr-defined]
    host.collapse_btn = _Caret()  # type: ignore[attr-defined]
    host._collapsed = False  # type: ignore[attr-defined]
    host._body_mode = "list"  # type: ignore[attr-defined]


class _RadarPane(CompactRadarHandlersMixin):
    def __init__(self) -> None:
        _pane_body(self)

    def Layout(self) -> None:
        pass

    def InvalidateBestSize(self) -> None:
        pass


class _GuidePane(CompactSideboardHandlersMixin):
    def __init__(self) -> None:
        _pane_body(self)

    def Layout(self) -> None:
        pass

    def InvalidateBestSize(self) -> None:
        pass


@pytest.mark.parametrize("pane_type", [_RadarPane, _GuidePane])
class TestPaneFolding:
    def test_folding_hides_the_whole_body(self, pane_type: type) -> None:
        pane = pane_type()

        pane.set_collapsed(True)

        assert pane.is_collapsed()
        assert pane.collapse_btn.collapsed
        assert not pane.card_list.shown
        assert not pane.status_label.shown
        assert not pane.empty_state.shown

    def test_an_update_while_folded_stays_folded(self, pane_type: type) -> None:
        """Polling keeps updating a folded pane; that must not unfold it."""
        pane = pane_type()
        pane.set_collapsed(True)

        pane._show_list()
        assert not pane.card_list.shown
        pane._show_empty("Waiting for opponent…")
        assert not pane.empty_state.shown

    def test_unfolding_brings_back_the_body_that_was_last_asked_for(self, pane_type: type) -> None:
        pane = pane_type()
        pane.set_collapsed(True)
        pane._show_empty("No deck pinned.")

        pane.set_collapsed(False)

        assert pane.empty_state.shown
        assert not pane.card_list.shown
        assert not pane.status_label.shown
        assert not pane.collapse_btn.collapsed
