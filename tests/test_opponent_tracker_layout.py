"""Layout regressions for the opponent tracker ("deck spy") window.

Every case here is a string that used to be unreadable in the real window: the
headline painted over the panels below it, the pane headings were cut off
mid-archetype, the sideboard notes ran off the right edge, and eight of the nine
format lines said "Unknown". The wx work itself (``Wrap``, sizer proportions) is
verified on screen; what is pinned here is the arithmetic and the filtering that
decide *what* those calls are given.
"""

from __future__ import annotations

import pytest

from utils.constants.ui_layout import (
    COMPACT_RADAR_HEADER_WRAP_MARGIN,
    COMPACT_SIDEBOARD_MIN_WRAP_WIDTH,
    COMPACT_SIDEBOARD_NOTE_WRAP_MARGIN,
)
from widgets.panels.compact_radar_panel.handlers import CompactRadarHandlersMixin
from widgets.panels.compact_sideboard_panel.handlers import CompactSideboardHandlersMixin


class _Size:
    """The one accessor the panels' width arithmetic uses off a wx size."""

    def __init__(self, width: int) -> None:
        self._width = width

    def GetWidth(self) -> int:
        return self._width


class _Label:
    def __init__(self) -> None:
        self.label = ""
        self.wrapped_to: int | None = None

    def SetLabel(self, text: str) -> None:
        self.label = text

    def Wrap(self, width: int) -> None:
        self.wrapped_to = width


class _Button:
    def __init__(self, width: int) -> None:
        self._width = width
        self.shown = True

    def IsShown(self) -> bool:
        return self.shown

    def GetSize(self) -> _Size:
        return _Size(self._width)


class _MeasuringList:
    """A list that measures text at a fixed width per character.

    A real ``wx.ListBox`` measures with its own proportional font; a fixed
    per-character width keeps the wrap arithmetic deterministic without giving
    up the fact that it *is* measured rather than counted in code units.
    """

    CHAR_WIDTH = 10

    def __init__(self, client_width: int) -> None:
        self.lines: list[str] = []
        self._client_width = client_width

    def GetClientSize(self) -> _Size:
        return _Size(self._client_width)

    def GetTextExtent(self, text: str) -> tuple[int, int]:
        return (len(text) * self.CHAR_WIDTH, 16)

    def Append(self, line: str) -> None:
        self.lines.append(line)

    def Clear(self) -> None:
        self.lines = []


class _SideboardHost(CompactSideboardHandlersMixin):
    def __init__(self, *, panel_width: int = 240, list_width: int = 240) -> None:
        self.header_label = _Label()
        self.toggle_btn = _Button(80)
        self.card_list = _MeasuringList(list_width)
        self._panel_width = panel_width
        self._current_entry: dict | None = None
        self._play_first = True
        self._header_text = ""
        self._resizing = False
        self.status_label = _Label()

    def GetClientSize(self) -> _Size:
        return _Size(self._panel_width)


class _RadarHost(CompactRadarHandlersMixin):
    def __init__(self, *, panel_width: int = 400, button_width: int = 96) -> None:
        self.header_label = _Label()
        self.view_toggle_btn = _Button(button_width)
        self._panel_width = panel_width
        self._header_text = ""
        self._resizing = False

    def GetClientSize(self) -> _Size:
        return _Size(self._panel_width)


class TestPaneHeadingsWrapToTheirPane:
    def test_radar_heading_wraps_to_the_measured_pane_width(self) -> None:
        host = _RadarHost(panel_width=400, button_width=96)

        host._set_header_text("Radar: Gruul Basking Broodscale Combo")

        assert host.header_label.label == "Radar: Gruul Basking Broodscale Combo"
        assert host.header_label.wrapped_to == 400 - 96 - COMPACT_RADAR_HEADER_WRAP_MARGIN

    def test_radar_heading_reclaims_the_toggle_width_while_it_is_hidden(self) -> None:
        host = _RadarHost(panel_width=400, button_width=96)
        host.view_toggle_btn.shown = False

        host._set_header_text("Radar: Loading...")

        assert host.header_label.wrapped_to == 400 - COMPACT_RADAR_HEADER_WRAP_MARGIN

    def test_guide_heading_wraps_to_the_measured_pane_width(self) -> None:
        host = _SideboardHost(panel_width=240)

        host._set_header_text("Guide: Gruul Basking Broodscale Combo")

        assert host.header_label.wrapped_to == 240 - 80 - COMPACT_SIDEBOARD_NOTE_WRAP_MARGIN

    @pytest.mark.parametrize("panel_width", [0, 40, 120])
    def test_heading_wrap_never_collapses_below_the_floor(self, panel_width: int) -> None:
        host = _SideboardHost(panel_width=panel_width)

        host._set_header_text("Guide: x")

        assert host.header_label.wrapped_to == COMPACT_SIDEBOARD_MIN_WRAP_WIDTH


class TestGuideNotesWrap:
    """``wx.ListBox`` neither wraps nor scrolls sideways, so the panel must."""

    def test_long_note_is_broken_into_lines_that_fit(self) -> None:
        # 240px of list minus the margin, at 10px per char -> 21 chars per line.
        host = _SideboardHost(list_width=240)

        lines = host._wrap_note_lines("They combo on turn two with Basking Broodscale")

        assert lines == ["They combo on turn", "two with Basking", "Broodscale"]
        assert all(len(line) * _MeasuringList.CHAR_WIDTH <= 212 for line in lines)

    def test_existing_line_breaks_are_kept(self) -> None:
        host = _SideboardHost(list_width=1000)

        assert host._wrap_note_lines("first\nsecond") == ["first", "second"]

    def test_a_word_longer_than_the_column_still_gets_a_line(self) -> None:
        host = _SideboardHost(list_width=140)

        assert host._wrap_note_lines("Bloodbraid") == ["Bloodbraid"]

    def test_notes_reach_the_list_wrapped(self) -> None:
        host = _SideboardHost(list_width=240)
        host._current_entry = {
            "play_out": {},
            "play_in": {},
            "notes": "They combo on turn two with Basking Broodscale",
        }

        host._populate_list()

        assert "  They combo on turn" in host.card_list.lines
        assert "  two with Basking" in host.card_list.lines


class TestUnknownFormatsAreNotDecks:
    def test_lookup_drops_the_unknown_sentinel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ "Unknown" is truthy, so every one of the nine formats used to show."""
        from widgets.frames.identify_opponent.handlers import polling as polling_module

        found = {"Modern": "Goryo's Vengeance", "Legacy": "Dimir Tempo"}
        monkeypatch.setattr(
            polling_module,
            "get_latest_deck",
            lambda player, fmt: found.get(fmt, "Unknown"),
        )

        class _Host(polling_module.OpponentPollingMixin):
            CACHE_TTL = 0

            def __init__(self) -> None:
                self.cache: dict = {}

            def _save_cache(self) -> None:
                pass

        assert _Host()._lookup_decks_all_formats("connormc02") == found
