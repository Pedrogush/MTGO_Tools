"""
Sideboard Guide Panel - Manages matchup-specific sideboarding strategies.

Allows users to create, edit, and manage guides for different matchups, including cards
to side in/out and matchup notes.
"""

from __future__ import annotations

from collections.abc import Callable

import wx
import wx.dataview as dv

from utils.constants import DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.constants.colors import FLEX_SLOT_BUTTON_COLOR, PIN_BUTTON_COLOR, WARNING_LABEL_COLOR
from utils.constants.ui_layout import (
    GUIDE_COL_ARCHETYPE_WIDTH,
    GUIDE_COL_CARDS_WIDTH,
    GUIDE_COL_NOTES_WIDTH,
    PADDING_MD,
)
from utils.i18n import translate
from utils.stylize import stylize_button


class SideboardGuidePanel(wx.Panel):
    """Panel that manages sideboard guides for matchups."""

    def __init__(
        self,
        parent: wx.Window,
        on_add_entry: Callable[[], None],
        on_edit_entry: Callable[[], None],
        on_remove_entry: Callable[[], None],
        on_edit_exclusions: Callable[[], None],
        on_export_csv: Callable[[], None],
        on_import_csv: Callable[[], None],
        on_pin_guide: Callable[[], None] | None = None,
        on_edit_flex_slots: Callable[[], None] | None = None,
        locale: str | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self._locale = locale

        self.on_add_entry = on_add_entry
        self.on_edit_entry = on_edit_entry
        self.on_remove_entry = on_remove_entry
        self.on_edit_exclusions = on_edit_exclusions
        self.on_export_csv = on_export_csv
        self.on_import_csv = on_import_csv
        self.on_pin_guide = on_pin_guide
        self.on_edit_flex_slots = on_edit_flex_slots

        self.entries: list[dict[str, str]] = []
        self.exclusions: list[str] = []

        self._build_ui()
        self._refresh_view()

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Guide entries list
        self.guide_view = dv.DataViewListCtrl(self, style=dv.DV_ROW_LINES)
        self.guide_view.AppendTextColumn(
            self._t("guide.col.archetype"), width=GUIDE_COL_ARCHETYPE_WIDTH
        )
        self.guide_view.AppendTextColumn(self._t("guide.col.play_out"), width=GUIDE_COL_CARDS_WIDTH)
        self.guide_view.AppendTextColumn(self._t("guide.col.play_in"), width=GUIDE_COL_CARDS_WIDTH)
        self.guide_view.AppendTextColumn(self._t("guide.col.draw_out"), width=GUIDE_COL_CARDS_WIDTH)
        self.guide_view.AppendTextColumn(self._t("guide.col.draw_in"), width=GUIDE_COL_CARDS_WIDTH)
        self.guide_view.AppendTextColumn(self._t("guide.col.notes"), width=GUIDE_COL_NOTES_WIDTH)
        self.guide_view.SetBackgroundColour(DARK_ALT)
        self.guide_view.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.guide_view, 1, wx.EXPAND | wx.ALL, PADDING_MD)

        # Empty state panel (shown when there are no entries)
        self.empty_state_panel = wx.Panel(self)
        self.empty_state_panel.SetBackgroundColour(DARK_ALT)
        empty_sizer = wx.BoxSizer(wx.VERTICAL)
        self.empty_state_panel.SetSizer(empty_sizer)
        empty_sizer.AddStretchSpacer(1)
        empty_label = wx.StaticText(
            self.empty_state_panel,
            label=self._t("guide.empty"),
            style=wx.ALIGN_CENTRE_HORIZONTAL,
        )
        empty_label.SetForegroundColour(SUBDUED_TEXT)
        empty_sizer.Add(empty_label, 0, wx.ALIGN_CENTER | wx.ALL, PADDING_MD)
        self.empty_cta_btn = wx.Button(self.empty_state_panel, label=self._t("guide.btn.cta"))
        stylize_button(self.empty_cta_btn)
        self.empty_cta_btn.Bind(wx.EVT_BUTTON, self._on_add_clicked)
        empty_sizer.Add(self.empty_cta_btn, 0, wx.ALIGN_CENTER | wx.ALL, PADDING_MD)
        empty_sizer.AddStretchSpacer(1)
        self.empty_state_panel.Hide()
        sizer.Add(self.empty_state_panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Button row (hidden in empty state)
        self.button_row = wx.Panel(self)
        self.button_row.SetBackgroundColour(DARK_PANEL)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.button_row.SetSizer(buttons)
        sizer.Add(self.button_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        self.add_btn = wx.Button(self.button_row, label=self._t("guide.btn.add"))
        stylize_button(self.add_btn)
        self.add_btn.Bind(wx.EVT_BUTTON, self._on_add_clicked)
        buttons.Add(self.add_btn, 0, wx.RIGHT, PADDING_MD)

        self.edit_btn = wx.Button(self.button_row, label=self._t("guide.btn.edit"))
        stylize_button(self.edit_btn)
        self.edit_btn.Bind(wx.EVT_BUTTON, self._on_edit_clicked)
        buttons.Add(self.edit_btn, 0, wx.RIGHT, PADDING_MD)

        self.remove_btn = wx.Button(self.button_row, label=self._t("guide.btn.delete"))
        stylize_button(self.remove_btn)
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove_clicked)
        buttons.Add(self.remove_btn, 0, wx.RIGHT, PADDING_MD)

        self.exclusions_btn = wx.Button(self.button_row, label=self._t("guide.btn.exclusions"))
        stylize_button(self.exclusions_btn)
        self.exclusions_btn.Bind(wx.EVT_BUTTON, self._on_exclusions_clicked)
        buttons.Add(self.exclusions_btn, 0, wx.RIGHT, PADDING_MD)

        self.export_btn = wx.Button(self.button_row, label=self._t("guide.btn.export"))
        stylize_button(self.export_btn)
        self.export_btn.Bind(wx.EVT_BUTTON, self._on_export_clicked)
        buttons.Add(self.export_btn, 0, wx.RIGHT, PADDING_MD)

        self.import_btn = wx.Button(self.button_row, label=self._t("guide.btn.import"))
        stylize_button(self.import_btn)
        self.import_btn.Bind(wx.EVT_BUTTON, self._on_import_clicked)
        buttons.Add(self.import_btn, 0, wx.RIGHT, PADDING_MD)

        self.flex_slots_btn = wx.Button(self.button_row, label=self._t("guide.btn.flex_slots"))
        stylize_button(self.flex_slots_btn)
        self.flex_slots_btn.SetBackgroundColour(wx.Colour(*FLEX_SLOT_BUTTON_COLOR))
        self.flex_slots_btn.SetToolTip(self._t("guide.tooltip.flex_slots"))
        self.flex_slots_btn.Bind(wx.EVT_BUTTON, self._on_flex_slots_clicked)
        if self.on_edit_flex_slots is None:
            self.flex_slots_btn.Disable()
        buttons.Add(self.flex_slots_btn, 0, wx.RIGHT, PADDING_MD)

        buttons.AddStretchSpacer(1)

        self.pin_btn = wx.Button(self.button_row, label=self._t("guide.btn.pin"))
        stylize_button(self.pin_btn)
        self.pin_btn.SetBackgroundColour(wx.Colour(*PIN_BUTTON_COLOR))
        self.pin_btn.SetToolTip(
            "Pin this deck's sideboard guide so the Opponent Tracker can look up matchup plans automatically."
        )
        self.pin_btn.Bind(wx.EVT_BUTTON, self._on_pin_clicked)
        if self.on_pin_guide is None:
            self.pin_btn.Disable()
        buttons.Add(self.pin_btn, 0)

        # Exclusions label
        self.exclusions_label = wx.StaticText(
            self, label=f"{self._t('guide.label.exclusions')}: \u2014"
        )
        self.exclusions_label.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.exclusions_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Warning label (hidden by default)
        self.warning_label = wx.StaticText(self, label="")
        self.warning_label.SetForegroundColour(wx.Colour(*WARNING_LABEL_COLOR))
        self.warning_label.Hide()
        sizer.Add(self.warning_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

    # ============= Public API =============

    def set_entries(
        self, entries: list[dict[str, str]], exclusions: list[str] | None = None
    ) -> None:
        self.entries = entries
        self.exclusions = exclusions or []
        self._refresh_view()

    def get_entries(self) -> list[dict[str, str]]:
        return self.entries

    def get_exclusions(self) -> list[str]:
        return self.exclusions

    def get_selected_index(self) -> int | None:
        item = self.guide_view.GetSelection()
        if not item.IsOk():
            return None
        return self.guide_view.ItemToRow(item)

    def clear(self) -> None:
        self.entries = []
        self.exclusions = []
        self._refresh_view()

    def set_warning(self, message: str) -> None:
        if message:
            self.warning_label.SetLabel(message)
            self.warning_label.Show()
        else:
            self.warning_label.Hide()
        self.Layout()

    # ============= Private Methods =============

    def _refresh_view(self) -> None:
        self.guide_view.DeleteAllItems()

        # Add entries (skip excluded archetypes)
        visible_entries = 0
        for entry in self.entries:
            if entry.get("archetype") in self.exclusions:
                continue
            self.guide_view.AppendItem(
                [
                    entry.get("archetype", ""),
                    self._format_card_list(entry.get("play_out", {})),
                    self._format_card_list(entry.get("play_in", {})),
                    self._format_card_list(entry.get("draw_out", {})),
                    self._format_card_list(entry.get("draw_in", {})),
                    entry.get("notes", ""),
                ]
            )
            visible_entries += 1

        # Toggle empty state visibility
        is_empty = visible_entries == 0
        self.guide_view.Show(not is_empty)
        self.empty_state_panel.Show(is_empty)
        self.button_row.Show(not is_empty)
        # GetHandle() returns 0 when the underlying HWND is not realized yet —
        # calling Layout() in that state asserts inside wxWindow::GetLayoutDirection.
        # Skip the explicit relayout; the parent sizer will lay the panel out
        # naturally once the frame is shown.
        if self.GetHandle():
            self.Layout()

        # Update exclusions label
        text = ", ".join(self.exclusions) if self.exclusions else "\u2014"
        self.exclusions_label.SetLabel(f"{self._t('guide.label.exclusions')}: {text}")

    def _format_card_list(self, cards: dict[str, int] | str) -> str:
        # Accepts either a dict (new format) or a plain string (old format).
        if isinstance(cards, str):
            # Old format - just return the string
            return cards

        if not cards:
            return ""

        # New format - dict of card name to quantity
        formatted = []
        for name, qty in sorted(cards.items()):
            formatted.append(f"{qty}x {name}")
        return ", ".join(formatted)

    def _on_add_clicked(self, _event: wx.Event) -> None:
        self.on_add_entry()

    def _on_edit_clicked(self, _event: wx.Event) -> None:
        self.on_edit_entry()

    def _on_remove_clicked(self, _event: wx.Event) -> None:
        self.on_remove_entry()

    def _on_exclusions_clicked(self, _event: wx.Event) -> None:
        self.on_edit_exclusions()

    def _on_export_clicked(self, _event: wx.Event) -> None:
        self.on_export_csv()

    def _on_import_clicked(self, _event: wx.Event) -> None:
        self.on_import_csv()

    def _on_pin_clicked(self, _event: wx.Event) -> None:
        if self.on_pin_guide:
            self.on_pin_guide()

    def _on_flex_slots_clicked(self, _event: wx.Event) -> None:
        if self.on_edit_flex_slots:
            self.on_edit_flex_slots()

    def set_pinned(self, pinned: bool) -> None:
        if pinned:
            self.pin_btn.SetLabel(self._t("guide.btn.pinned"))
        else:
            self.pin_btn.SetLabel(self._t("guide.btn.pin"))
