"""Top Cards widget for browsing locally cached format card-pool totals."""

# ruff: noqa: E402

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import wx

from services.format_card_pool_service import (
    FormatCardPoolService,
    get_format_card_pool_service,
)
from utils.constants import DARK_ALT, DARK_BG, DARK_PANEL, FORMAT_OPTIONS, LIGHT_TEXT, SUBDUED_TEXT
from utils.i18n import translate


class TopCardsFrame(wx.Frame):
    """Widget for browsing the most-played cards in each format."""

    def __init__(
        self,
        parent: wx.Window | None = None,
        locale: str | None = None,
        format_card_pool_service: FormatCardPoolService | None = None,
    ) -> None:
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.top_cards"),
            size=(760, 700),
            style=style,
        )
        self._locale = locale
        self._service = format_card_pool_service or get_format_card_pool_service()
        self.current_format = "modern"

        self._build_ui()
        self.Centre(wx.BOTH)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        wx.CallAfter(self.refresh_data)

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(main_sizer)

        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(toolbar, 0, wx.ALL | wx.EXPAND, 10)

        label = wx.StaticText(panel, label=self._t("top_cards.label.format"))
        label.SetForegroundColour(LIGHT_TEXT)
        toolbar.Add(label, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 5)

        self.format_choice = wx.Choice(panel, choices=list(FORMAT_OPTIONS))
        self.format_choice.SetSelection(list(FORMAT_OPTIONS).index("Modern"))
        self.format_choice.SetBackgroundColour(DARK_ALT)
        self.format_choice.SetForegroundColour(LIGHT_TEXT)
        self.format_choice.Bind(wx.EVT_CHOICE, self.on_format_change)
        toolbar.Add(self.format_choice, 0, wx.RIGHT, 15)

        self.refresh_button = wx.Button(panel, label=self._t("top_cards.btn.refresh"))
        self._stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self.refresh_data())
        toolbar.Add(self.refresh_button, 0, wx.RIGHT, 10)

        toolbar.AddStretchSpacer(1)

        self.status_label = wx.StaticText(panel, label="")
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(self.status_label, 0, wx.ALIGN_CENTER_VERTICAL)

        self.card_list = wx.ListCtrl(panel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        self.card_list.InsertColumn(0, self._t("top_cards.col.rank"), width=60)
        self.card_list.InsertColumn(1, self._t("top_cards.col.card"), width=450)
        self.card_list.InsertColumn(2, self._t("top_cards.col.copies"), width=120)
        self.card_list.SetBackgroundColour(DARK_PANEL)
        self.card_list.SetForegroundColour(LIGHT_TEXT)
        main_sizer.Add(self.card_list, 1, wx.ALL | wx.EXPAND, 10)

    def _stylize_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    def on_format_change(self, _event: wx.CommandEvent) -> None:
        self.current_format = self.format_choice.GetStringSelection().lower()
        self.refresh_data()

    def refresh_data(self) -> None:
        """Reload the card list from the local cache."""
        format_name = self.current_format
        summary = self._service.get_summary(format_name)
        top_cards = self._service.get_top_cards(format_name)

        self.card_list.DeleteAllItems()
        if summary is None or not top_cards:
            self.status_label.SetLabel(
                self._t("top_cards.status.no_data", format=format_name.title())
            )
            return

        self.status_label.SetLabel(
            self._t(
                "top_cards.status.loaded",
                decks=summary.total_decks_analyzed,
                unique_cards=summary.unique_cards,
                generated_at=summary.generated_at,
            )
        )
        for index, entry in enumerate(top_cards, start=1):
            row = self.card_list.InsertItem(self.card_list.GetItemCount(), str(index))
            self.card_list.SetItem(row, 1, entry.card_name)
            self.card_list.SetItem(row, 2, str(entry.copies_played))

    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()
