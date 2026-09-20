"""UI construction for the deck history tab.

Layout is a header strip (which branch, and a picker to change it) over a
horizontal split: the painted graph on the left, and the selected version's
decklist plus its diff on the right. The diff's baseline defaults to the
selected commit's parent -- which is what someone reading a history wants nine
times out of ten -- and can be pinned to any node from its context menu.

The decklist and diff views are monospaced on purpose: a unified diff's leading
``+``/``-`` column and the card counts under it only line up in a fixed-pitch
face. The *size* still comes from the type ladder, so only the face departs from
the app's UI font.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

import wx

from utils.constants.theme import SPACE_SM, SPACE_XS, SURFACE_PANEL
from utils.i18n import translate
from widgets.input_frame import create_text_input
from widgets.notebook import make_flat_notebook
from widgets.panels.deck_history_panel.graph_canvas import DeckGraphCanvas
from widgets.panels.deck_history_panel.handlers import DeckHistoryPanelHandlersMixin
from widgets.splitter import DarkSplitter
from widgets.stylize import stylize_button, stylize_choice, stylize_label, type_font

if TYPE_CHECKING:
    from services.deck_vcs_service import DeckVcsService

#: Fixed-pitch face for the decklist and diff views. ``SetFaceName`` fails
#: harmlessly when it is absent, leaving the UI face.
MONO_FACE = "Consolas"

#: Where the split between graph and preview starts.
GRAPH_PANE_WIDTH = 520
MIN_PANE_WIDTH = 180


class DeckHistoryPanel(DeckHistoryPanelHandlersMixin, wx.Panel):
    """Panel showing a deck's version graph, with preview and diff."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        vcs_service: DeckVcsService | None = None,
        deck_repo: Any = None,
        on_checkout: Callable[[str], None] | None = None,
        on_status_update: Callable[..., None] | None = None,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))

        if vcs_service is None:
            from services.deck_vcs_service import get_deck_vcs_service

            vcs_service = get_deck_vcs_service()
        if deck_repo is None:
            from repositories.deck_repository import get_deck_repository

            deck_repo = get_deck_repository()

        self.vcs_service = vcs_service
        self.deck_repo = deck_repo
        self.locale = locale
        self._on_checkout = on_checkout
        self._on_status_update = on_status_update

        self._graph = []
        self._baseline_sha: str | None = None
        self._selected_sha: str | None = None

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(self._build_header(), 0, wx.EXPAND | wx.ALL, SPACE_XS)
        sizer.Add(self._build_body(), 1, wx.EXPAND | wx.ALL, SPACE_XS)
        self.SetSizer(sizer)

    # ------------------------------------------------------------------ construction ------------------------------------------------------------------
    def _build_header(self) -> wx.Sizer:
        row = wx.BoxSizer(wx.HORIZONTAL)

        self.branch_label = wx.StaticText(self, label=self._t("history.no_branch"))
        stylize_label(self.branch_label, level="caption", surface="panel")
        row.Add(self.branch_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        picker_label = wx.StaticText(self, label=self._t("history.branch.label"))
        stylize_label(picker_label, level="caption", surface="panel")
        row.Add(picker_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)

        self.branch_choice = wx.Choice(self, choices=[])
        stylize_choice(self.branch_choice, surface="panel")
        self.branch_choice.Bind(wx.EVT_CHOICE, self.on_branch_chosen)
        self.branch_choice.SetToolTip(self._t("history.branch.tooltip"))
        row.Add(self.branch_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        refresh = wx.Button(self, label=self._t("history.refresh"))
        stylize_button(refresh, "secondary", surface="panel")
        refresh.Bind(wx.EVT_BUTTON, lambda _e: self.refresh_history())
        row.Add(refresh, 0, wx.ALIGN_CENTER_VERTICAL)

        row.AddStretchSpacer()
        self.baseline_label = wx.StaticText(self, label=self._t("history.baseline.none"))
        stylize_label(self.baseline_label, level="caption", surface="panel")
        row.Add(self.baseline_label, 0, wx.ALIGN_CENTER_VERTICAL)
        return row

    def _build_body(self) -> wx.Window:
        split = DarkSplitter(self)
        split.SetMinimumPaneSize(MIN_PANE_WIDTH)
        split.SetSashGravity(0.55)

        self.graph_canvas = DeckGraphCanvas(
            split,
            on_select=self.on_node_selected,
            on_context=self.on_node_context,
            empty_text=self._t("history.empty"),
        )

        right = wx.Panel(split)
        right.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))
        right_sizer = wx.BoxSizer(wx.VERTICAL)
        notebook = make_flat_notebook(right)
        self.preview_tabs = notebook

        preview_frame = self._make_mono_field(notebook)
        self.preview_text = preview_frame.ctrl
        notebook.AddPage(preview_frame, self._t("history.tab.decklist"))

        diff_frame = self._make_mono_field(notebook)
        self.diff_text = diff_frame.ctrl
        notebook.AddPage(diff_frame, self._t("history.tab.diff"))

        right_sizer.Add(notebook, 1, wx.EXPAND)
        right.SetSizer(right_sizer)

        split.SplitVertically(self.graph_canvas, right, GRAPH_PANE_WIDTH)
        return split

    def _make_mono_field(self, parent: wx.Window) -> wx.Window:
        """A read-only, fixed-pitch multiline field inside the app's input frame."""
        field = create_text_input(
            parent,
            level="caption",
            surface="panel",
            style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_DONTWRAP,
        )
        font = type_font("caption")
        font.SetFaceName(MONO_FACE)
        field.ctrl.SetFont(font)
        return field

    # ------------------------------------------------------------------ context ------------------------------------------------------------------
    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self.locale, key, **kwargs)

    def current_deck_key(self) -> str:
        from services.deck_vcs_service import deck_key_for

        return deck_key_for(self.deck_repo.get_current_deck(), self.current_deck_file())

    def current_deck_file(self) -> Path | None:
        """The user's own ``.txt`` for the loaded deck, when it came from one.

        ``None`` for a deck that has no file behind it (a scraped list, an
        average): there is nothing on disk a checkout should rewrite, so the
        version history moves and the file system is left alone.
        """
        deck = self.deck_repo.get_current_deck()
        if not deck:
            return None
        path = deck.get("path")
        return Path(path) if path else None
