"""Dialog for creating/editing sideboard guide entries with interactive card selection."""

from __future__ import annotations

from typing import Any

import wx

from utils.constants import DARK_ALT, DARK_BG, LIGHT_TEXT
from utils.i18n import translate
from widgets.panels.sideboard_card_selector import SideboardCardSelector


class GuideEntryDialog(wx.Dialog):
    """Dialog for editing a sideboard guide entry with card selection from mainboard/sideboard."""

    def __init__(
        self,
        parent: wx.Window,
        archetype_names: list[str],
        mainboard_cards: list[dict[str, Any]],
        sideboard_cards: list[dict[str, Any]],
        data: dict[str, Any] | None = None,
        flex_slots: list[str] | None = None,
        locale: str | None = None,
    ) -> None:
        """
        Initialize the guide entry dialog.

        Args:
            parent: Parent window
            archetype_names: List of archetype names for dropdown
            mainboard_cards: List of mainboard cards available to take out
            sideboard_cards: List of sideboard cards available to bring in
            data: Existing entry data to edit (optional)
            flex_slots: Card names marked as flex slots (highlighted in Out selectors)
            locale: Locale code for i18n
        """
        self._locale = locale
        super().__init__(parent, title="Sideboard Guide Entry", size=(1100, 750))

        main_sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(main_sizer)

        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        panel_sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(panel_sizer)
        main_sizer.Add(panel, 1, wx.EXPAND | wx.ALL, 8)

        # Archetype
        archetype_label = wx.StaticText(panel, label=self._t("guide.dialog.archetype_matchup"))
        archetype_label.SetForegroundColour(LIGHT_TEXT)
        panel_sizer.Add(archetype_label, 0, wx.TOP | wx.LEFT, 4)

        initial_choices = sorted({name for name in archetype_names if name})
        self.archetype_ctrl = wx.ComboBox(panel, choices=initial_choices, style=wx.CB_DROPDOWN)
        self.archetype_ctrl.SetBackgroundColour(DARK_ALT)
        self.archetype_ctrl.SetForegroundColour(LIGHT_TEXT)
        if data and data.get("archetype"):
            existing = {
                self.archetype_ctrl.GetString(i) for i in range(self.archetype_ctrl.GetCount())
            }
            if data["archetype"] not in existing:
                self.archetype_ctrl.Append(data["archetype"])
            self.archetype_ctrl.SetValue(data["archetype"])
        panel_sizer.Add(self.archetype_ctrl, 0, wx.EXPAND | wx.ALL, 4)

        # Play scenario section
        play_label = wx.StaticText(panel, label=self._t("guide.dialog.on_the_play"))
        play_label.SetForegroundColour(LIGHT_TEXT)
        play_label.SetFont(play_label.GetFont().Bold())
        panel_sizer.Add(play_label, 0, wx.TOP | wx.LEFT, 8)

        play_sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_sizer.Add(play_sizer, 1, wx.EXPAND | wx.ALL, 4)

        # Play: Out (from mainboard)
        self.play_out_selector = SideboardCardSelector(
            panel,
            self._t("guide.dialog.out_from_main"),
            mainboard_cards,
            flex_slots=flex_slots,
            locale=locale,
        )
        play_sizer.Add(self.play_out_selector, 1, wx.EXPAND | wx.RIGHT, 4)

        # Play: In (from sideboard)
        self.play_in_selector = SideboardCardSelector(
            panel, self._t("guide.dialog.in_from_side"), sideboard_cards, locale=locale
        )
        play_sizer.Add(self.play_in_selector, 1, wx.EXPAND)

        # Draw scenario section
        draw_label = wx.StaticText(panel, label=self._t("guide.dialog.on_the_draw"))
        draw_label.SetForegroundColour(LIGHT_TEXT)
        draw_label.SetFont(draw_label.GetFont().Bold())
        panel_sizer.Add(draw_label, 0, wx.TOP | wx.LEFT, 8)

        draw_sizer = wx.BoxSizer(wx.HORIZONTAL)
        panel_sizer.Add(draw_sizer, 1, wx.EXPAND | wx.ALL, 4)

        # Draw: Out (from mainboard)
        self.draw_out_selector = SideboardCardSelector(
            panel,
            self._t("guide.dialog.out_from_main"),
            mainboard_cards,
            flex_slots=flex_slots,
            locale=locale,
        )
        draw_sizer.Add(self.draw_out_selector, 1, wx.EXPAND | wx.RIGHT, 4)

        # Draw: In (from sideboard)
        self.draw_in_selector = SideboardCardSelector(
            panel, self._t("guide.dialog.in_from_side"), sideboard_cards, locale=locale
        )
        draw_sizer.Add(self.draw_in_selector, 1, wx.EXPAND)

        # Notes section
        notes_label = wx.StaticText(panel, label=self._t("guide.dialog.notes_label"))
        notes_label.SetForegroundColour(LIGHT_TEXT)
        panel_sizer.Add(notes_label, 0, wx.TOP | wx.LEFT, 8)

        self.notes_ctrl = wx.TextCtrl(
            panel, value=(data or {}).get("notes", ""), style=wx.TE_MULTILINE, size=(-1, 80)
        )
        self.notes_ctrl.SetBackgroundColour(DARK_ALT)
        self.notes_ctrl.SetForegroundColour(LIGHT_TEXT)
        self.notes_ctrl.SetHint(self._t("guide.dialog.notes_hint"))
        panel_sizer.Add(self.notes_ctrl, 0, wx.EXPAND | wx.ALL, 4)

        # Enable double entries checkbox
        self.enable_double_checkbox = wx.CheckBox(
            panel, label=self._t("guide.dialog.double_entries")
        )
        self.enable_double_checkbox.SetForegroundColour(LIGHT_TEXT)
        self.enable_double_checkbox.SetToolTip(
            "If unchecked, will overwrite existing entries for this archetype. "
            "If checked, will add new entry even if archetype already exists."
        )
        panel_sizer.Add(self.enable_double_checkbox, 0, wx.ALL, 8)

        # Custom button sizer with Save & Continue
        button_sizer = wx.BoxSizer(wx.HORIZONTAL)

        # Save & Continue button (custom ID)
        self.save_continue_btn = wx.Button(
            panel, label=self._t("guide.dialog.save_continue"), id=wx.ID_APPLY
        )
        self.save_continue_btn.Bind(wx.EVT_BUTTON, self._on_save_continue)
        button_sizer.Add(self.save_continue_btn, 0, wx.RIGHT, 8)

        button_sizer.AddStretchSpacer()

        # OK button
        ok_btn = wx.Button(panel, label="OK", id=wx.ID_OK)
        ok_btn.SetDefault()
        ok_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_OK))
        button_sizer.Add(ok_btn, 0, wx.RIGHT, 8)

        # Cancel button
        cancel_btn = wx.Button(panel, label=self._t("guide.dialog.cancel"), id=wx.ID_CANCEL)
        cancel_btn.Bind(wx.EVT_BUTTON, lambda evt: self.EndModal(wx.ID_CANCEL))
        button_sizer.Add(cancel_btn, 0)

        panel_sizer.Add(button_sizer, 0, wx.EXPAND | wx.ALL, 8)

        # Load existing data if provided
        if data:
            self._load_data(data)

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _on_save_continue(self, event: wx.Event) -> None:
        """Handle Save & Continue button click."""
        # Return wx.ID_APPLY to signal save without closing
        self.EndModal(wx.ID_APPLY)

    def _load_data(self, data: dict[str, Any]) -> None:
        """Load existing data into the selectors."""
        # Load play out/in
        if "play_out" in data:
            self.play_out_selector.set_selected_cards(data["play_out"])
        if "play_in" in data:
            self.play_in_selector.set_selected_cards(data["play_in"])

        # Load draw out/in
        if "draw_out" in data:
            self.draw_out_selector.set_selected_cards(data["draw_out"])
        if "draw_in" in data:
            self.draw_in_selector.set_selected_cards(data["draw_in"])

    def get_data(self) -> dict[str, Any]:
        """Get the guide entry data."""
        return {
            "archetype": self.archetype_ctrl.GetValue().strip(),
            "play_out": self.play_out_selector.get_selected_cards(),
            "play_in": self.play_in_selector.get_selected_cards(),
            "draw_out": self.draw_out_selector.get_selected_cards(),
            "draw_in": self.draw_in_selector.get_selected_cards(),
            "notes": self.notes_ctrl.GetValue().strip(),
            "enable_double_entries": self.enable_double_checkbox.GetValue(),
        }
