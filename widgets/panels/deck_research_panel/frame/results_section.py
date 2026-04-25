"""Deck-results section construction (action buttons, archetype summary, deck list)."""

from __future__ import annotations

import wx
import wx.html

from utils.constants import DARK_PANEL, LIGHT_TEXT, PADDING_MD
from widgets.buttons.deck_action_buttons import DeckActionButtons
from widgets.lists.deck_results_list import DeckResultsList


class ResultsSectionBuilderMixin:
    """Builds the deck-action button row, archetype summary box, and deck list.

    Kept as a mixin (no ``__init__``) so :class:`DeckResearchPanel` remains the
    single source of truth for instance-state initialization.
    """

    deck_action_buttons: DeckActionButtons
    summary_text: wx.html.HtmlWindow
    deck_list: DeckResultsList
    daily_average_button: wx.Button
    copy_button: wx.Button
    load_button: wx.Button
    save_button: wx.Button

    def _build_deck_results_section(self, sizer: wx.Sizer) -> None:
        self.deck_action_buttons = DeckActionButtons(
            self,
            on_copy=self._on_copy,
            on_save=self._on_save,
            on_daily_average=self._on_daily_average,
            on_load=self._on_load,
            labels={
                "daily_average": self._labels.get("daily_average", "Today's Average"),
                "copy": self._labels.get("copy", "Copy"),
                "load_deck": self._labels.get("load_deck", "Load Deck"),
                "save_deck": self._labels.get("save_deck", "Save Deck"),
                "daily_average_tooltip": self._labels.get("daily_average_tooltip", ""),
                "copy_tooltip": self._labels.get("copy_tooltip", ""),
                "load_deck_tooltip": self._labels.get("load_deck_tooltip", ""),
                "save_deck_tooltip": self._labels.get("save_deck_tooltip", ""),
            },
        )
        sizer.Add(
            self.deck_action_buttons, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD
        )

        summary_box = wx.StaticBox(
            self, label=self._labels.get("archetype_summary", "Archetype Summary")
        )
        summary_box.SetForegroundColour(LIGHT_TEXT)
        summary_box.SetBackgroundColour(DARK_PANEL)
        summary_sizer = wx.StaticBoxSizer(summary_box, wx.VERTICAL)

        self.summary_text = wx.html.HtmlWindow(
            summary_box,
            style=wx.html.HW_SCROLLBAR_NEVER | wx.NO_BORDER,
        )
        self.summary_text.SetBackgroundColour(wx.Colour(34, 39, 46))
        self.summary_text.SetBorders(-1)
        self.summary_text.SetMinSize((-1, 62))
        summary_sizer.Add(self.summary_text, 1, wx.EXPAND)
        sizer.Add(summary_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        results_box = wx.StaticBox(self, label=self._labels.get("deck_results", "Deck Results"))
        results_box.SetForegroundColour(LIGHT_TEXT)
        results_box.SetBackgroundColour(DARK_PANEL)
        results_sizer = wx.StaticBoxSizer(results_box, wx.VERTICAL)

        self.deck_list = DeckResultsList(results_box)
        if self._on_deck_selected is not None:
            self.deck_list.Bind(wx.EVT_LISTBOX, lambda _evt: self._on_deck_selected())  # type: ignore[misc]
        results_sizer.Add(self.deck_list, 1, wx.EXPAND | wx.ALL, PADDING_MD)
        sizer.Add(results_sizer, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        self.daily_average_button = self.deck_action_buttons.daily_average_button
        self.copy_button = self.deck_action_buttons.copy_button
        self.load_button = self.deck_action_buttons.load_button
        self.save_button = self.deck_action_buttons.save_button
