"""UI construction for the Patterns tab.

A header strip (what the numbers mean, which turn, and a refresh) over a tree:
one node per distinct land combination, with that combination's maximal plays
as its children.

The header says "capability ceiling" and keeps saying it. The two assumptions
behind the analysis -- the whole decklist in hand, and no state carried between
turns -- make these numbers an upper bound on what the deck *could* do, not a
projection of what it is likely to do, and a reader who takes one for the other
will badly overrate the deck. That is a labelling problem, so it is solved with
a permanent label rather than a tooltip someone has to go looking for.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

from services.deck_patterns_service import (
    DEFAULT_MAX_TURN,
    PatternsOptions,
)
from utils.constants.theme import SPACE_SM, SPACE_XS, SURFACE_ALT, SURFACE_PANEL, TEXT_PRIMARY
from utils.i18n import translate
from widgets.panels.deck_patterns_panel.handlers import DeckPatternsPanelHandlersMixin
from widgets.stylize import stylize_button, stylize_choice, stylize_label

if TYPE_CHECKING:
    from services.deck_patterns_service import DeckPatternsService
    from utils.background_worker import BackgroundWorker


class DeckPatternsPanel(DeckPatternsPanelHandlersMixin, wx.Panel):
    """Panel showing, per turn, what the deck could cast off each land mix."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        patterns_service: DeckPatternsService | None = None,
        card_manager: Any = None,
        worker: BackgroundWorker | None = None,
        options: PatternsOptions | None = None,
        on_status_update: Callable[..., None] | None = None,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))

        if patterns_service is None:
            from services.deck_patterns_service import get_deck_patterns_service

            patterns_service = get_deck_patterns_service(card_manager)

        self.patterns_service = patterns_service
        self.worker = worker
        self.locale = locale
        self.options = options or PatternsOptions()
        self._on_status_update = on_status_update

        self.zone_cards: dict[str, list[dict[str, Any]]] = {}
        self._result = None
        self._pending = False
        self._dirty = True
        self._run_token = 0

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._build_header(), 0, wx.EXPAND | wx.ALL, SPACE_XS)
        sizer.Add(self._build_tree(), 1, wx.EXPAND | wx.ALL, SPACE_XS)
        self.SetSizer(sizer)

        self.render()

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self.locale, key, **kwargs)

    # ------------------------------------------------------------------ construction ------------------------------------------------------------------
    def _build_header(self) -> wx.Sizer:
        header = wx.BoxSizer(wx.VERTICAL)

        self.ceiling_label = wx.StaticText(self, label=self._t("patterns.ceiling"))
        stylize_label(self.ceiling_label, level="caption", tone="secondary", surface="panel")
        header.Add(self.ceiling_label, 0, wx.BOTTOM, SPACE_XS)

        row = wx.BoxSizer(wx.HORIZONTAL)

        turn_label = wx.StaticText(self, label=self._t("patterns.turn"))
        stylize_label(turn_label, level="body", surface="panel")
        row.Add(turn_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)

        self.turn_choice = wx.Choice(
            self, choices=[str(n) for n in range(1, self.options.max_turn + 1)]
        )
        self.turn_choice.SetSelection(0)
        self.turn_choice.SetToolTip(self._t("patterns.turn.tooltip"))
        stylize_choice(self.turn_choice)
        self.turn_choice.Bind(wx.EVT_CHOICE, self.on_turn_changed)
        row.Add(self.turn_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        self.refresh_button = wx.Button(self, label=self._t("patterns.refresh"))
        stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, self.on_refresh)
        row.Add(self.refresh_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        self.status_label = wx.StaticText(self, label="")
        stylize_label(self.status_label, level="body", tone="secondary", surface="panel")
        row.Add(self.status_label, 1, wx.ALIGN_CENTER_VERTICAL)

        header.Add(row, 0, wx.EXPAND)
        return header

    def _build_tree(self) -> wx.Window:
        # NO_BORDER keeps the native sunken client edge off, the same way the
        # rules browser's tree does; the colours come from the theme tokens.
        self.tree = wx.TreeCtrl(
            self,
            style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.NO_BORDER,
        )
        self.tree.SetBackgroundColour(wx.Colour(*SURFACE_ALT))
        self.tree.SetForegroundColour(wx.Colour(*TEXT_PRIMARY))
        return self.tree


__all__ = ["DEFAULT_MAX_TURN", "DeckPatternsPanel"]
