"""UI construction for the sideboard guide panel.

Manages matchup-specific sideboarding strategies, allowing users to create, edit, and
manage guides for different matchups, including cards to side in/out and matchup notes.
"""

from __future__ import annotations

from collections.abc import Callable

import wx
import wx.dataview as dv

from utils.constants import DARK_ALT, DARK_PANEL, LIGHT_TEXT, SUBDUED_TEXT
from utils.constants.colors import WARNING_LABEL_COLOR
from utils.constants.ui_layout import (
    GUIDE_COL_ARCHETYPE_WIDTH,
    GUIDE_COL_CARDS_WIDTH,
    GUIDE_COL_NOTES_WIDTH,
    SPACE_SM,
)
from widgets.empty_state import EmptyState
from widgets.panels.sideboard_guide_panel.handlers import SideboardGuidePanelHandlersMixin
from widgets.panels.sideboard_guide_panel.properties import SideboardGuidePanelPropertiesMixin
from widgets.stylize import stylize_button, stylize_scrollable


class SideboardGuidePanel(
    SideboardGuidePanelHandlersMixin,
    SideboardGuidePanelPropertiesMixin,
    wx.Panel,
):
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
        on_record_guide: Callable[[], None] | None = None,
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
        self.on_record_guide = on_record_guide

        self.entries: list[dict[str, str]] = []
        self.exclusions: list[str] = []

        self._build_ui()
        self._refresh_view()

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
        # After the columns, so the native header child exists to be themed.
        stylize_scrollable(self.guide_view)
        sizer.Add(self.guide_view, 1, wx.EXPAND | wx.ALL, SPACE_SM)

        # C5/C6: this was the app's best empty state and still had the copy bug --
        # it said `click "Add"` while its own CTA read "Add your first matchup".
        # Now the shared component, with copy that names no button at all.
        self.empty_state_panel = EmptyState(
            self,
            message=self._t("guide.empty"),
            hint=self._t("guide.empty.hint"),
            cta_label=self._t("guide.btn.cta"),
            on_cta=self._on_add_clicked,
            secondary_label=self._t("guide.btn.record"),
            on_secondary=self._on_record_clicked,
            surface="alt",
        )
        self.empty_cta_btn = self.empty_state_panel.cta_button
        self.empty_record_btn = self.empty_state_panel.secondary_button
        self.empty_record_btn.SetToolTip(self._t("guide.tooltip.record"))
        if self.on_record_guide is None:
            self.empty_record_btn.Disable()
        self.empty_state_panel.Hide()
        sizer.Add(self.empty_state_panel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)

        # Button row (hidden in empty state)
        self.button_row = wx.Panel(self)
        self.button_row.SetBackgroundColour(DARK_PANEL)
        buttons = wx.BoxSizer(wx.HORIZONTAL)
        self.button_row.SetSizer(buttons)
        sizer.Add(self.button_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)

        self.add_btn = wx.Button(self.button_row, label=self._t("guide.btn.add"))
        stylize_button(self.add_btn, kind="primary")
        self.add_btn.Bind(wx.EVT_BUTTON, self._on_add_clicked)
        buttons.Add(self.add_btn, 0, wx.RIGHT, SPACE_SM)

        self.record_btn = wx.Button(self.button_row, label=self._t("guide.btn.record"))
        stylize_button(self.record_btn, kind="secondary")
        self.record_btn.SetToolTip(self._t("guide.tooltip.record"))
        self.record_btn.Bind(wx.EVT_BUTTON, self._on_record_clicked)
        if self.on_record_guide is None:
            self.record_btn.Disable()
        buttons.Add(self.record_btn, 0, wx.RIGHT, SPACE_SM)

        self.edit_btn = wx.Button(self.button_row, label=self._t("guide.btn.edit"))
        stylize_button(self.edit_btn, kind="secondary")
        self.edit_btn.Bind(wx.EVT_BUTTON, self._on_edit_clicked)
        buttons.Add(self.edit_btn, 0, wx.RIGHT, SPACE_SM)

        self.remove_btn = wx.Button(self.button_row, label=self._t("guide.btn.delete"))
        # The one destructive control in the row; it was indistinguishable from
        # "Export" before.
        stylize_button(self.remove_btn, kind="danger")
        self.remove_btn.Bind(wx.EVT_BUTTON, self._on_remove_clicked)
        buttons.Add(self.remove_btn, 0, wx.RIGHT, SPACE_SM)

        self.exclusions_btn = wx.Button(self.button_row, label=self._t("guide.btn.exclusions"))
        stylize_button(self.exclusions_btn, kind="secondary")
        self.exclusions_btn.Bind(wx.EVT_BUTTON, self._on_exclusions_clicked)
        buttons.Add(self.exclusions_btn, 0, wx.RIGHT, SPACE_SM)

        self.export_btn = wx.Button(self.button_row, label=self._t("guide.btn.export"))
        stylize_button(self.export_btn, kind="secondary")
        self.export_btn.Bind(wx.EVT_BUTTON, self._on_export_clicked)
        buttons.Add(self.export_btn, 0, wx.RIGHT, SPACE_SM)

        self.import_btn = wx.Button(self.button_row, label=self._t("guide.btn.import"))
        stylize_button(self.import_btn, kind="secondary")
        self.import_btn.Bind(wx.EVT_BUTTON, self._on_import_clicked)
        buttons.Add(self.import_btn, 0, wx.RIGHT, SPACE_SM)

        self.flex_slots_btn = wx.Button(self.button_row, label=self._t("guide.btn.flex_slots"))
        stylize_button(self.flex_slots_btn, kind="success")
        self.flex_slots_btn.SetToolTip(self._t("guide.tooltip.flex_slots"))
        self.flex_slots_btn.Bind(wx.EVT_BUTTON, self._on_flex_slots_clicked)
        if self.on_edit_flex_slots is None:
            self.flex_slots_btn.Disable()
        buttons.Add(self.flex_slots_btn, 0, wx.RIGHT, SPACE_SM)

        buttons.AddStretchSpacer(1)

        self.pin_btn = wx.Button(self.button_row, label=self._t("guide.btn.pin"))
        # Retires PIN_BUTTON_COLOR, a bespoke purple with no semantic role and
        # the contrast suite's one documented xfail.
        stylize_button(self.pin_btn, kind="secondary")
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
        sizer.Add(self.exclusions_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)

        # Warning label (hidden by default)
        self.warning_label = wx.StaticText(self, label="")
        self.warning_label.SetForegroundColour(wx.Colour(*WARNING_LABEL_COLOR))
        self.warning_label.Hide()
        sizer.Add(self.warning_label, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_SM)
