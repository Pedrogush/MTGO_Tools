"""UI construction for the Goldfish tab (issue #1045).

A toolbar -- *New hand*, *Mulligan*, *Draw*, and a status line -- over
:class:`~widgets.panels.deck_goldfish_panel.table_view.GoldfishTableView`, which
is where every pixel of the hand and the play area is painted.

The split is the one the rest of the deck workspace uses: the rules-free game
state lives in :class:`~services.deck_service.goldfish.GoldfishTable` (wx-free,
seedable, unit-tested), the art pipeline in
:mod:`~widgets.panels.deck_goldfish_panel.card_art`, the geometry in
:mod:`~widgets.panels.deck_goldfish_panel.layout`, and this class owns only the
widgets and the wiring between them.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import wx

from services.deck_service.goldfish import GoldfishTable
from utils.constants import SPACE_SM, SPACE_XS, VIEW_TOGGLE_HEIGHT, VIEW_TOGGLE_PADDING_X
from utils.constants.theme import SURFACE_PANEL
from utils.i18n import translate
from widgets.panels.deck_goldfish_panel.card_art import GoldfishArtCache
from widgets.panels.deck_goldfish_panel.handlers import DeckGoldfishPanelHandlersMixin
from widgets.panels.deck_goldfish_panel.table_view import GoldfishTableView
from widgets.stylize import size_compact_button, stylize_button, stylize_label


class DeckGoldfishPanel(DeckGoldfishPanelHandlersMixin, wx.Panel):
    """Deal opening hands off the loaded deck and play them out on a table."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        get_card_image: Callable[[str, str], Path | None],
        get_metadata: Callable[[str], Any],
        locale: str | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))
        self._locale = locale

        # ``seed`` is for the harness and for tests; the app leaves it None and
        # gets ``random``'s own seeding, which is what a shuffle should have.
        self.table = GoldfishTable(seed=seed)
        self._art = GoldfishArtCache(get_card_image, get_metadata, self._on_art_ready)

        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        self.new_hand_button = self._toolbar_button(
            toolbar,
            self._t("tabs.goldfish.new_hand"),
            self._t("tabs.goldfish.new_hand.tooltip"),
            self._on_new_hand,
            kind="primary",
        )
        self.mulligan_button = self._toolbar_button(
            toolbar,
            self._t("tabs.goldfish.mulligan"),
            self._t("tabs.goldfish.mulligan.tooltip"),
            self._on_mulligan,
        )
        self.draw_button = self._toolbar_button(
            toolbar,
            self._t("tabs.goldfish.draw"),
            self._t("tabs.goldfish.draw.tooltip"),
            self._on_draw,
        )

        # The status line takes the row's slack and ellipsises rather than
        # pushing the buttons off the panel -- the same three ingredients the
        # deck workspace's own labels need (see ``create_status_label``).
        self.status_label = wx.StaticText(
            self,
            label=self._t("tabs.goldfish.no_deck"),
            style=wx.ST_ELLIPSIZE_END | wx.ST_NO_AUTORESIZE,
        )
        stylize_label(self.status_label, level="caption", surface="panel", tone="secondary")
        toolbar.Add(self.status_label, 1, wx.ALIGN_CENTER_VERTICAL | wx.LEFT, SPACE_SM)
        outer.Add(toolbar, 0, wx.EXPAND | wx.ALL, SPACE_SM)

        self._view = GoldfishTableView(
            self,
            self.table,
            self._art,
            self._refresh_status,
            self._t("tabs.goldfish.empty"),
        )
        self._view.SetToolTip(self._t("tabs.goldfish.hint"))
        outer.Add(self._view, 1, wx.EXPAND)

        self._refresh_status()

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _toolbar_button(
        self,
        sizer: wx.BoxSizer,
        label: str,
        tooltip: str,
        handler: Callable[[wx.CommandEvent], None],
        *,
        kind: str = "secondary",
    ) -> wx.Button:
        """One chip in the toolbar, sized like the deck workspace's view toggles."""
        button = wx.Button(self, label=label, style=wx.BU_EXACTFIT)
        stylize_button(button, kind=kind, surface="panel")
        size_compact_button(button, pad_x=VIEW_TOGGLE_PADDING_X, height=VIEW_TOGGLE_HEIGHT)
        button.SetToolTip(tooltip)
        button.Bind(wx.EVT_BUTTON, handler)
        sizer.Add(button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)
        return button
