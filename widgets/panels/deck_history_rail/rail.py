"""The rail itself: a caption, the branch it is on, and the version column."""

from __future__ import annotations

from collections.abc import Callable

import wx

from services.deck_vcs_service import HistorySnapshot
from utils.constants import DECK_HISTORY_RAIL_WIDTH
from utils.constants.theme import SPACE_XS, SURFACE_PANEL
from utils.i18n import translate
from widgets.panels.deck_history_rail.canvas import DeckRailCanvas
from widgets.section import SectionPanel
from widgets.stylize import stylize_label
from widgets.wx_layout import set_shown


class DeckHistoryRail(wx.Panel):
    """A narrow column of the loaded deck's versions, beside the deck tables.

    Fed rather than self-reading: :meth:`set_snapshot` takes the history the
    frame has already read for the History tab, so having the rail on screen
    costs no extra trip into the deck's repo.
    """

    def __init__(
        self,
        parent: wx.Window,
        *,
        on_checkout: Callable[[str], None] | None = None,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))
        self.locale = locale
        self._on_checkout = on_checkout

        section = SectionPanel(self, title=None, padding=SPACE_XS)
        body = section.body

        self.caption = wx.StaticText(
            body,
            label=self._t("history.rail.title"),
            style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE,
        )
        self.caption.SetMinSize((0, -1))
        stylize_label(self.caption, level="caption", surface="panel")
        section.sizer.Add(self.caption, 0, wx.EXPAND | wx.BOTTOM, SPACE_XS)

        # A branch name is user-supplied and the rail is 104px wide, so this
        # would otherwise run off the strip mid-word. ``ST_ELLIPSIZE_END`` only
        # takes effect from the *constructor*, and needs ``ST_NO_AUTORESIZE``
        # plus a zero floor to stop the label reporting its full text as its
        # minimum size and widening the strip instead.
        self.branch_label = wx.StaticText(
            body, label="", style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE
        )
        self.branch_label.SetMinSize((0, -1))
        stylize_label(self.branch_label, level="caption", surface="panel")
        section.sizer.Add(self.branch_label, 0, wx.EXPAND | wx.BOTTOM, SPACE_XS)

        self.canvas = DeckRailCanvas(
            body,
            on_activate=self._activate,
            empty_text=self._t("history.rail.empty"),
        )
        self.canvas.SetToolTip(self._t("history.rail.tooltip"))
        section.sizer.Add(self.canvas, 1, wx.EXPAND)

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(section, 1, wx.EXPAND)
        self.SetSizer(sizer)

        self.SetMinSize((DECK_HISTORY_RAIL_WIDTH, -1))
        self.SetMaxSize((DECK_HISTORY_RAIL_WIDTH, -1))

    # ------------------------------------------------------------------ state ------------------------------------------------------------------
    def set_snapshot(self, snapshot: HistorySnapshot) -> None:
        """Show a history the frame has already read."""
        from widgets.panels.deck_history_panel.layout import build_layout

        self.Freeze()
        try:
            self.canvas.set_layout(build_layout(list(snapshot.graph)))
            branch = snapshot.current_branch
            self.branch_label.SetLabel(branch or "")
            # ``set_shown`` rather than Show + Layout: hiding the branch line on
            # a deck with no history leaves repaint ghosts otherwise (see
            # ``tests/test_layout_repaint_guard.py``).
            set_shown(self.branch_label, bool(branch), relayout_from=self)
        finally:
            self.Thaw()

    def _activate(self, sha: str) -> None:
        if self._on_checkout is not None:
            self._on_checkout(sha)

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self.locale, key, **kwargs)
