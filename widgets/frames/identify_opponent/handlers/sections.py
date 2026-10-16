"""Folding the tracker's sections down to their headings.

Each of the three sections (calculator, radar, sideboard guide) has a caret in
its heading. Folding one hides its body and hands the space to whatever is
still open: a folded calculator gives its height to the radar, a folded radar
gives it back to the calculator, and a folded guide gives its width to the left
column. The folded set is saved with the window position.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import (
    OPPONENT_TRACKER_GUIDE_COLUMN_PROPORTION,
    OPPONENT_TRACKER_GUIDE_MIN_WIDTH,
    OPPONENT_TRACKER_LEFT_COLUMN_PROPORTION,
    OPPONENT_TRACKER_LEFT_MIN_PANE_SIZE,
    OPPONENT_TRACKER_MIN_SIZE,
)
from widgets.frames.identify_opponent.sections import (
    SECTION_CALCULATOR,
    SECTION_GUIDE,
    SECTION_RADAR,
    column_proportions,
    left_sash_target,
)
from widgets.wx_layout import relayout

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class SectionCollapseMixin(_Base):
    """Per-section fold/unfold, and the layout that follows from it."""

    def _bind_section_toggles(self) -> None:
        toggles = {
            SECTION_CALCULATOR: self.calc_collapse_btn,
            SECTION_RADAR: self.radar_panel.collapse_btn,
            SECTION_GUIDE: self.sideboard_panel.collapse_btn,
        }
        for name, toggle in toggles.items():
            toggle.set_tooltips(
                collapse=self._t("tracker.tooltip.collapse_section"),
                expand=self._t("tracker.tooltip.expand_section"),
            )
            toggle.Bind(wx.EVT_BUTTON, lambda _evt, n=name: self._toggle_section(n))

    def _is_section_collapsed(self, name: str) -> bool:
        return name in self._collapsed_sections

    def _toggle_section(self, name: str) -> None:
        if name in self._collapsed_sections:
            self._collapsed_sections.discard(name)
        else:
            self._collapsed_sections.add(name)
        self._apply_section_visibility()
        # A fold is a request for a fresh layout, so it overrides a sash the
        # user dragged earlier -- otherwise folding the radar would leave the
        # sash wherever it was and the freed space would just sit empty.
        self._sash_user_set = False
        self._refit_left_splitter()
        relayout(self._content_panel)
        self._persist_config_async()

    def _apply_section_visibility(self) -> None:
        """Show or hide each section's body and re-weight the two columns.

        Does not move the sash: at construction the splitter has no height yet,
        so the first sash placement waits for ``_fit_left_splitter``.
        """
        calc_folded = self._is_section_collapsed(SECTION_CALCULATOR)
        radar_folded = self._is_section_collapsed(SECTION_RADAR)
        guide_folded = self._is_section_collapsed(SECTION_GUIDE)

        self.calc_collapse_btn.set_collapsed(calc_folded)
        self.calc_panel.GetSizer().Show(self._calc_body_sizer, not calc_folded, recursive=True)
        self.calc_panel.InvalidateBestSize()
        relayout(self.calc_panel)

        self.radar_panel.set_collapsed(radar_folded)
        self.sideboard_panel.set_collapsed(guide_folded)

        # A folded guide is only as wide as its heading; an open one keeps the
        # floor that stops its notes wrapping a word per line.
        guide_min_w = -1 if guide_folded else OPPONENT_TRACKER_GUIDE_MIN_WIDTH
        self.sideboard_panel.SetMinSize(wx.Size(guide_min_w, -1))

        left_prop, guide_prop = column_proportions(
            self._collapsed_sections,
            left_proportion=OPPONENT_TRACKER_LEFT_COLUMN_PROPORTION,
            guide_proportion=OPPONENT_TRACKER_GUIDE_COLUMN_PROPORTION,
        )
        self._main_sizer.GetItem(self._left_splitter).SetProportion(left_prop)
        self._main_sizer.GetItem(self.sideboard_panel).SetProportion(guide_prop)

        # The pane floor has to let a folded pane shrink to its heading.
        if calc_folded or radar_folded:
            folded_heights = []
            if calc_folded:
                folded_heights.append(self.calc_panel.GetBestSize().GetHeight())
            if radar_folded:
                folded_heights.append(self.radar_panel.GetBestSize().GetHeight())
            self._left_splitter.SetMinimumPaneSize(min(folded_heights))
        else:
            self._left_splitter.SetMinimumPaneSize(OPPONENT_TRACKER_LEFT_MIN_PANE_SIZE)

        # The minimum window size exists so every *open* section is whole; with
        # something folded the user may want the window smaller than that.
        # Never *above* the normal minimum, though: the content's own minimum
        # can be wider than it (the guide's floor plus the calculator).
        if self._collapsed_sections:
            self.SetMinSize(wx.DefaultSize)
            self.SetMinClientSize(self._content_panel.GetSizer().CalcMin())
            folded_min = self.GetMinSize()
            full_w, full_h = OPPONENT_TRACKER_MIN_SIZE
            self.SetMinSize(
                wx.Size(min(folded_min.GetWidth(), full_w), min(folded_min.GetHeight(), full_h))
            )
        else:
            self.SetMinSize(wx.Size(*OPPONENT_TRACKER_MIN_SIZE))

    def _left_sash_target(self) -> int:
        self.calc_panel.InvalidateBestSize()
        self.radar_panel.InvalidateBestSize()
        return left_sash_target(
            calc_collapsed=self._is_section_collapsed(SECTION_CALCULATOR),
            radar_collapsed=self._is_section_collapsed(SECTION_RADAR),
            calc_height=self.calc_panel.GetBestSize().GetHeight(),
            radar_height=self.radar_panel.GetBestSize().GetHeight(),
            splitter_height=self._left_splitter.GetClientSize().GetHeight(),
            sash_size=self._left_splitter.GetSashSize(),
        )
