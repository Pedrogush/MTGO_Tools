"""UI construction for the Baseline tab.

A header saying which archetype is being measured and at what cut-off, over a
tree of the three groups: staples, partial staples with their floor, and the
ranked flex candidates.

The tab deliberately has no format/archetype pickers of its own. The app
already has one pair, in the research panel, and a second pair here would let
the two disagree about what the user is looking at. It reads that selection
instead, so "the baseline of the thing I am looking at" is the only thing it
can ever show.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import wx

from utils.constants.theme import SPACE_SM, SPACE_XS, SURFACE_ALT, SURFACE_PANEL, TEXT_PRIMARY
from utils.i18n import translate
from widgets.panels.deck_baseline_panel.handlers import (
    THRESHOLD_CHOICES,
    DeckBaselinePanelHandlersMixin,
)
from widgets.stylize import stylize_button, stylize_choice, stylize_label

if TYPE_CHECKING:
    from services.archetype_baseline_service import ArchetypeBaselineService
    from utils.background_worker import BackgroundWorker

#: Index of the default cut-off in :data:`THRESHOLD_CHOICES` (90%).
DEFAULT_THRESHOLD_INDEX = 2


class DeckBaselinePanel(DeckBaselinePanelHandlersMixin, wx.Panel):
    """Panel showing an archetype's staples, partial staples and flex slots."""

    def __init__(
        self,
        parent: wx.Window,
        *,
        baseline_service: ArchetypeBaselineService | None = None,
        worker: BackgroundWorker | None = None,
        archetype_provider: Callable[[], dict[str, Any] | None] | None = None,
        format_provider: Callable[[], str] | None = None,
        on_status_update: Callable[..., None] | None = None,
        locale: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.SetBackgroundColour(wx.Colour(*SURFACE_PANEL))

        if baseline_service is None:
            from services.archetype_baseline_service import get_archetype_baseline_service

            baseline_service = get_archetype_baseline_service()

        self.baseline_service = baseline_service
        self.worker = worker
        self.locale = locale

        self._archetype_provider = archetype_provider
        self._format_provider = format_provider
        self._on_status_update = on_status_update

        self._baseline: Any = None
        self._pending = False
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

        self.explainer_label = wx.StaticText(self, label=self._t("baseline.explainer"))
        stylize_label(self.explainer_label, level="caption", tone="secondary", surface="panel")
        header.Add(self.explainer_label, 0, wx.BOTTOM, SPACE_XS)

        self.target_label = wx.StaticText(self, label=self._t("baseline.target.none"))
        stylize_label(self.target_label, level="body", surface="panel")
        header.Add(self.target_label, 0, wx.BOTTOM, SPACE_XS)

        row = wx.BoxSizer(wx.HORIZONTAL)

        threshold_label = wx.StaticText(self, label=self._t("baseline.threshold"))
        stylize_label(threshold_label, level="body", surface="panel")
        row.Add(threshold_label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_XS)

        self.threshold_choice = wx.Choice(
            self, choices=[label for label, _value in THRESHOLD_CHOICES]
        )
        self.threshold_choice.SetSelection(DEFAULT_THRESHOLD_INDEX)
        self.threshold_choice.SetToolTip(self._t("baseline.threshold.tooltip"))
        stylize_choice(self.threshold_choice)
        self.threshold_choice.Bind(wx.EVT_CHOICE, self.on_threshold_changed)
        row.Add(self.threshold_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        self.compute_button = wx.Button(self, label=self._t("baseline.compute"))
        self.compute_button.SetToolTip(self._t("baseline.compute.tooltip"))
        stylize_button(self.compute_button)
        self.compute_button.Bind(wx.EVT_BUTTON, self.on_compute)
        self.compute_button.Enable(False)
        row.Add(self.compute_button, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, SPACE_SM)

        self.status_label = wx.StaticText(self, label="")
        stylize_label(self.status_label, level="body", tone="secondary", surface="panel")
        row.Add(self.status_label, 1, wx.ALIGN_CENTER_VERTICAL)

        header.Add(row, 0, wx.EXPAND)
        return header

    def _build_tree(self) -> wx.Window:
        # NO_BORDER for the same reason as the Patterns tree: the native sunken
        # client edge is the one part of the control no colour call reaches.
        self.tree = wx.TreeCtrl(
            self,
            style=wx.TR_HAS_BUTTONS | wx.TR_HIDE_ROOT | wx.TR_LINES_AT_ROOT | wx.NO_BORDER,
        )
        self.tree.SetBackgroundColour(wx.Colour(*SURFACE_ALT))
        self.tree.SetForegroundColour(wx.Colour(*TEXT_PRIMARY))
        return self.tree


__all__ = ["DEFAULT_THRESHOLD_INDEX", "DeckBaselinePanel"]
