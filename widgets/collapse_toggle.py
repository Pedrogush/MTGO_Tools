"""The caret button that folds a pane down to its heading and back.

Sits at the left of a pane heading. It only shows and reports state; what
collapsing actually hides (and how the surrounding layout gives the space away)
is the owner's job, because only the owner knows what else shares the space.
"""

from __future__ import annotations

import wx

from utils.constants.ui_layout import SECTION_COLLAPSE_BTN_SIZE
from widgets.stylize import stylize_button

#: Points down at the content it would fold away.
EXPANDED_GLYPH = "▼"
#: Points at the heading it would unfold from. Same pair as the main window's
#: side-panel toggles (◀/▶), so it renders with the same font fallback.
COLLAPSED_GLYPH = "▶"


class CollapseToggle(wx.Button):
    """A small ghost button showing ▼ while its pane is open and ▶ while folded.

    Clicking emits a plain ``wx.EVT_BUTTON``; the owner flips its own state and
    calls :meth:`set_collapsed` with the result. The button never flips itself,
    so a click the owner refuses leaves the glyph telling the truth.
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        surface: str = "panel",
    ) -> None:
        super().__init__(
            parent,
            label=EXPANDED_GLYPH,
            size=SECTION_COLLAPSE_BTN_SIZE,
            style=wx.BU_EXACTFIT,
        )
        self.SetMinSize(SECTION_COLLAPSE_BTN_SIZE)
        self._collapse_tooltip = ""
        self._expand_tooltip = ""
        self._collapsed = False
        stylize_button(self, kind="ghost", surface=surface)
        self._sync()

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_tooltips(self, *, collapse: str, expand: str) -> None:
        """Tooltips for each state, set by the owner (which has the locale)."""
        self._collapse_tooltip = collapse
        self._expand_tooltip = expand
        self._sync()

    def set_collapsed(self, collapsed: bool) -> None:
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        self._sync()

    def _sync(self) -> None:
        self.SetLabel(COLLAPSED_GLYPH if self._collapsed else EXPANDED_GLYPH)
        tooltip = self._expand_tooltip if self._collapsed else self._collapse_tooltip
        if tooltip:
            self.SetToolTip(tooltip)
