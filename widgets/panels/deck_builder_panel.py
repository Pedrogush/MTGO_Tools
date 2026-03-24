from __future__ import annotations

from collections.abc import Callable
from typing import Any

import wx

from services.radar_service import RadarData
from utils.constants import (
    BUILDER_MANA_ALL_BTN_SIZE,
    BUILDER_MANA_CANVAS_WIDTH,
    BUILDER_MANA_ICON_GAP,
    BUILDER_MANA_ROW_HEIGHT,
    BUILDER_NAME_COL_DEFAULT_WIDTH,
    BUILDER_NAME_COL_MIN_WIDTH,
    BUILDER_SEARCH_DEBOUNCE_MS,
    DARK_ALT,
    DARK_PANEL,
    FORMAT_OPTIONS,
    LIGHT_TEXT,
    PADDING_MD,
    PADDING_SM,
    PADDING_XS,
    SUBDUED_TEXT,
)
from utils.mana_icon_factory import ManaIconFactory
from utils.stylize import (
    stylize_button,
    stylize_choice,
    stylize_label,
    stylize_textctrl,
)
from widgets.buttons.mana_button import create_mana_button


class _SearchResultsView(wx.ListCtrl):
    """Virtual ListCtrl for efficiently displaying large card search results."""

    def __init__(self, parent: wx.Window, style: int, mana_icons: ManaIconFactory | None = None):
        super().__init__(parent, style=style | wx.LC_REPORT | wx.LC_VIRTUAL | wx.LC_SINGLE_SEL)
        self._data: list[dict[str, Any]] = []
        self._mana_icons = mana_icons
        self._mana_img_index: dict[str, int] = {}
        self._mana_img_list: wx.ImageList | None = None
        if mana_icons:
            self._mana_img_list = wx.ImageList(BUILDER_MANA_CANVAS_WIDTH, BUILDER_MANA_ROW_HEIGHT)
            self.AssignImageList(self._mana_img_list, wx.IMAGE_LIST_SMALL)
        self.Bind(wx.EVT_SIZE, self._on_size)

    def _on_size(self, event: wx.SizeEvent) -> None:
        """Resize Name column to fill available width so no blank third column appears."""
        event.Skip()
        self._fit_name_column()

    def _fit_name_column(self) -> None:
        """Set Name column (index 1) width to consume all space left by Mana Cost column."""
        name_w = max(
            BUILDER_NAME_COL_MIN_WIDTH, self.GetClientSize().width - BUILDER_MANA_CANVAS_WIDTH
        )
        self.SetColumnWidth(1, name_w)

    def SetData(self, data: list[dict[str, Any]]) -> None:
        """Set the data source and refresh the display."""
        self._data = data
        if self._mana_icons and self._mana_img_list is not None:
            self._update_mana_cache()
        if self.GetItemCount() > 0:
            self.EnsureVisible(0)
        self.SetItemCount(len(data))
        self.Refresh()

    def _update_mana_cache(self) -> None:
        """Add bitmaps for mana costs not yet in the persistent image list.

        The image list is created once and only grows — existing indices are
        stable so OnGetItemColumnImage lookups remain valid across searches.
        Only costs absent from the cache require bitmap rendering, making
        repeated searches (including empty-filter / browse-all) O(new_costs).
        """
        from utils.mana_icon_factory import tokenize_mana_symbols

        assert self._mana_icons is not None
        assert self._mana_img_list is not None
        unique_costs = {card.get("mana_cost", "") for card in self._data if card.get("mana_cost")}
        new_costs = unique_costs - set(self._mana_img_index)
        if not new_costs:
            return

        for cost in new_costs:
            tokens = tokenize_mana_symbols(cost)
            if not tokens:
                continue

            # Collect render-scale bitmaps (before the factory's own downscale).
            # Using hires gives a single downscale from ~78px to the final size
            # instead of two chained downscales (78→26, then 26→final).
            raws: list[wx.Bitmap] = []
            for token in tokens:
                raw = self._mana_icons.bitmap_for_symbol_hires(token)
                if raw and raw.IsOk():
                    raws.append(raw)
            if not raws:
                continue

            # Compute each symbol's width if scaled to full row height.
            widths_at_full_h = [
                (
                    max(1, int(b.GetWidth() * BUILDER_MANA_ROW_HEIGHT / b.GetHeight()))
                    if b.GetHeight() > 0
                    else 1
                )
                for b in raws
            ]
            total_at_full_h = sum(widths_at_full_h) + max(0, len(raws) - 1) * BUILDER_MANA_ICON_GAP

            # Single squeeze factor: 1.0 when icons fit, <1.0 when they overflow.
            squeeze = (
                min(1.0, BUILDER_MANA_CANVAS_WIDTH / total_at_full_h)
                if total_at_full_h > 0
                else 1.0
            )
            final_h = max(1, int(BUILDER_MANA_ROW_HEIGHT * squeeze))

            # Single-pass scale: raw → final size.
            scaled_icons: list[wx.Bitmap] = []
            for bmp, w_full in zip(raws, widths_at_full_h):
                final_w = max(1, int(w_full * squeeze))
                scaled_icons.append(
                    wx.Bitmap(bmp.ConvertToImage().Scale(final_w, final_h, wx.IMAGE_QUALITY_HIGH))
                )

            total_w = (
                sum(b.GetWidth() for b in scaled_icons)
                + max(0, len(scaled_icons) - 1) * BUILDER_MANA_ICON_GAP
            )

            # DARK_ALT canvas — gaps between icons match the list background.
            canvas = wx.Bitmap(BUILDER_MANA_CANVAS_WIDTH, BUILDER_MANA_ROW_HEIGHT)
            dc = wx.MemoryDC(canvas)
            dc.SetBackground(wx.Brush(DARK_ALT))
            dc.Clear()

            # Right-justify: start at (canvas_width - total_icon_width).
            x = BUILDER_MANA_CANVAS_WIDTH - total_w
            for idx, icon_bmp in enumerate(scaled_icons):
                y = (BUILDER_MANA_ROW_HEIGHT - icon_bmp.GetHeight()) // 2
                dc.DrawBitmap(icon_bmp, x, max(0, y), False)
                x += icon_bmp.GetWidth()
                if idx < len(scaled_icons) - 1:
                    x += BUILDER_MANA_ICON_GAP

            dc.SelectObject(wx.NullBitmap)
            self._mana_img_index[cost] = self._mana_img_list.Add(canvas)

    def OnGetItemText(self, item: int, column: int) -> str:
        """Return text for the given item and column.

        Column layout:
          0 - hidden dummy (absorbs the IMAGE_LIST_SMALL indent, zero width)
          1 - card Name
          2 - Mana Cost text (suppressed when an icon image is shown)
        """
        if item < 0 or item >= len(self._data):
            return ""

        card = self._data[item]
        if column == 1:
            return card.get("name", "Unknown")
        elif column == 2:
            # Mana cost column: suppress text when an icon image is shown.
            cost = card.get("mana_cost", "")
            if self._mana_icons and cost in self._mana_img_index:
                return ""
            return cost if cost else "—"
        return ""

    def OnGetItemImage(self, item: int) -> int:
        """No image on the hidden dummy column 0."""
        return -1

    def OnGetItemColumnImage(self, item: int, col: int) -> int:
        """Return the image-list index for the mana cost icon (column 2)."""
        if col != 2 or not self._mana_icons or item < 0 or item >= len(self._data):
            return -1
        cost = self._data[item].get("mana_cost", "")
        return self._mana_img_index.get(cost, -1)

    def GetItemText(self, row: int, col: int = 0) -> str:
        """Legacy method for test compatibility.

        Callers use logical columns (0=Name, 1=Mana Cost); shift by 1 internally
        to account for the hidden dummy column 0.
        """
        return self.OnGetItemText(row, col + 1)


class DeckBuilderPanel(wx.Panel):
    """Panel for searching and filtering MTG cards by various properties."""

    def __init__(
        self,
        parent: wx.Window,
        mana_icons: ManaIconFactory,
        on_switch_to_research: Callable[[], None],
        on_ensure_card_data: Callable[[], None],
        open_mana_keyboard: Callable[[], None],
        on_search: Callable[[], None],
        on_clear: Callable[[], None],
        on_result_selected: Callable[[int | None], None],
        on_open_radar_dialog: Callable[[], RadarData | None] | None = None,
        on_add_to_main: Callable[[str], None] | None = None,
        on_add_to_side: Callable[[str], None] | None = None,
        on_add_to_active_zone: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent)

        # Store dependencies
        self.mana_icons = mana_icons
        self._on_switch_to_research = on_switch_to_research
        self._on_ensure_card_data = on_ensure_card_data
        self._open_mana_keyboard = open_mana_keyboard
        self._on_search_callback = on_search
        self._on_clear_callback = on_clear
        self._on_result_selected_callback = on_result_selected
        self._on_open_radar_dialog = on_open_radar_dialog
        self._on_add_to_main = on_add_to_main
        self._on_add_to_side = on_add_to_side
        self._on_add_to_active_zone = on_add_to_active_zone

        # State variables
        self.inputs: dict[str, wx.TextCtrl] = {}
        self.mana_exact_cb: wx.CheckBox | None = None
        self.mv_comparator: wx.Choice | None = None
        self.mv_value: wx.TextCtrl | None = None
        self.format_choice: wx.Choice | None = None
        self.color_checks: dict[str, wx.ToggleButton] = {}
        self.color_mode_choice: wx.Choice | None = None
        self.text_mode_choice: wx.Choice | None = None
        self.results_ctrl: _SearchResultsView | None = None
        self.status_label: wx.StaticText | None = None
        self._add_main_btn: wx.Button | None = None
        self._add_side_btn: wx.Button | None = None
        self.results_cache: list[dict[str, Any]] = []
        self._search_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_search_timer, self._search_timer)

        # Radar state
        self.active_radar: RadarData | None = None
        self.radar_enabled: bool = False
        self.radar_zone: str = "both"  # "mainboard", "sideboard", or "both"

        # Build the UI
        self._build_ui()

    def _build_ui(self) -> None:
        """Build the complete UI for the deck builder panel."""
        self.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # Back button
        back_btn = wx.Button(self, label="Deck Research")
        stylize_button(back_btn)
        back_btn.SetToolTip("Switch back to Deck Research mode")
        back_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_back_clicked())
        sizer.Add(back_btn, 0, wx.EXPAND | wx.ALL, PADDING_MD)

        # Info label
        info = wx.StaticText(self, label="Deck Builder: search MTG cards by property.")
        stylize_label(info, True)
        sizer.Add(info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Search fields
        field_specs = [
            ("name", "Card Name", "e.g. Ragavan", "Filter cards by name"),
            (
                "type",
                "Type Line",
                "Artifact Creature",
                "Filter cards by type line (e.g. Creature, Instant)",
            ),
            (
                "mana",
                "Mana Cost",
                "Curly braces like {1}{G} or shorthand (e.g. GGG)",
                "Filter cards by mana cost",
            ),
            ("text", "Oracle Text", "Keywords or abilities", "Filter cards by oracle text"),
        ]
        for key, label_text, hint, tooltip in field_specs:
            lbl = wx.StaticText(self, label=label_text)
            stylize_label(lbl, True)
            sizer.Add(lbl, 0, wx.LEFT | wx.RIGHT, PADDING_MD)
            ctrl = wx.TextCtrl(self)
            stylize_textctrl(ctrl)
            ctrl.SetHint(hint)
            ctrl.SetToolTip(tooltip)
            ctrl.Bind(wx.EVT_TEXT, self._on_filters_changed)
            self.inputs[key] = ctrl

            # Oracle Text field gets match-mode selector on same row as input
            if key == "text":
                text_row = wx.BoxSizer(wx.HORIZONTAL)
                text_row.Add(ctrl, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)
                text_mode_choice = wx.Choice(self, choices=["=", "≈"])
                text_mode_choice.SetSelection(0)
                stylize_choice(text_mode_choice)
                text_mode_choice.SetToolTip("= matches all words; ≈ matches any word")
                self.text_mode_choice = text_mode_choice
                text_mode_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
                text_row.Add(text_mode_choice, 0, wx.ALIGN_CENTER_VERTICAL)
                sizer.Add(text_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)
            else:
                sizer.Add(ctrl, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

            # Mana cost field gets extra controls
            if key == "mana":
                # Exact match checkbox
                match_row = wx.BoxSizer(wx.HORIZONTAL)
                match_label = wx.StaticText(self, label="Match")
                stylize_label(match_label, True)
                match_row.Add(match_label, 0, wx.RIGHT, PADDING_MD)
                exact_cb = wx.CheckBox(self, label="Exact symbols")
                exact_cb.SetForegroundColour(LIGHT_TEXT)
                exact_cb.SetBackgroundColour(DARK_PANEL)
                exact_cb.SetToolTip(
                    "When checked, match the exact mana symbols (no extras allowed)"
                )
                match_row.Add(exact_cb, 0)
                self.mana_exact_cb = exact_cb
                exact_cb.Bind(wx.EVT_CHECKBOX, self._on_filters_changed)
                match_row.AddStretchSpacer(1)
                sizer.Add(match_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_XS)

                # Mana symbol keyboard
                keyboard_row = wx.BoxSizer(wx.HORIZONTAL)
                keyboard_row.AddStretchSpacer(1)
                for token in ["W", "U", "B", "R", "G", "C", "X"]:
                    btn = create_mana_button(self, token, self._append_mana_symbol, self.mana_icons)
                    keyboard_row.Add(btn, 0, wx.ALL, PADDING_XS)
                all_btn = wx.Button(self, label="All", size=BUILDER_MANA_ALL_BTN_SIZE)
                stylize_button(all_btn)
                all_btn.SetToolTip("Open the full mana symbol keyboard")
                all_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._open_mana_keyboard())
                keyboard_row.Add(all_btn, 0, wx.ALL, PADDING_XS)
                keyboard_row.AddStretchSpacer(1)
                sizer.Add(
                    keyboard_row,
                    0,
                    wx.ALIGN_CENTER_HORIZONTAL | wx.LEFT | wx.RIGHT | wx.BOTTOM,
                    PADDING_XS,
                )

        # Mana value filter
        mv_label = wx.StaticText(self, label="Mana Value Filter")
        stylize_label(mv_label, True)
        sizer.Add(mv_label, 0, wx.LEFT | wx.RIGHT, PADDING_MD)
        mv_row = wx.BoxSizer(wx.HORIZONTAL)
        mv_value = wx.TextCtrl(self)
        stylize_textctrl(mv_value)
        mv_value.SetHint("e.g. 3")
        mv_value.SetToolTip("Enter a mana value (converted mana cost) to filter by")
        self.mv_value = mv_value
        mv_value.Bind(wx.EVT_TEXT, self._on_filters_changed)
        mv_row.Add(mv_value, 1, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)
        mv_choice = wx.Choice(self, choices=["-", "<", "≤", "=", "≥", ">"])
        mv_choice.SetSelection(0)
        stylize_choice(mv_choice)
        mv_choice.SetToolTip("Comparison operator for the mana value filter")
        self.mv_comparator = mv_choice
        mv_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        mv_row.Add(mv_choice, 0, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(mv_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

        # Color identity filter (left) + Format filter (right) on same line
        color_format_row = wx.BoxSizer(wx.HORIZONTAL)

        color_col = wx.BoxSizer(wx.VERTICAL)
        color_label = wx.StaticText(self, label="Color Identity Filter")
        stylize_label(color_label, True)
        color_col.Add(color_label, 0, wx.BOTTOM, PADDING_XS)
        color_controls = wx.BoxSizer(wx.HORIZONTAL)
        color_mode = wx.Choice(self, choices=["-", "≥", "=", "≠"])
        color_mode.SetSelection(0)
        stylize_choice(color_mode)
        color_mode.SetToolTip("≥ includes, = exactly, ≠ excludes the selected colors")
        self.color_mode_choice = color_mode
        color_mode.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        color_controls.Add(color_mode, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_SM)
        _color_names = {
            "W": "White",
            "U": "Blue",
            "B": "Black",
            "R": "Red",
            "G": "Green",
            "C": "Colorless",
        }
        _FILTER_ICON_SIZE = 32
        for code in ["W", "U", "B", "R", "G", "C"]:
            bmp: wx.Bitmap | None = None
            try:
                bmp = self.mana_icons.bitmap_for_symbol(code)
            except Exception:
                bmp = None
            if bmp and bmp.IsOk():
                scaled = wx.Bitmap(
                    bmp.ConvertToImage().Scale(
                        _FILTER_ICON_SIZE, _FILTER_ICON_SIZE, wx.IMAGE_QUALITY_HIGH
                    )
                )
                grey_bmp = wx.Bitmap(scaled.ConvertToImage().ConvertToGreyscale())
                btn_size = (_FILTER_ICON_SIZE + 10, _FILTER_ICON_SIZE + 10)
                btn: wx.ToggleButton = wx.BitmapToggleButton(
                    self, wx.ID_ANY, grey_bmp, size=btn_size
                )
                btn.SetBitmapPressed(scaled)
            else:
                btn = wx.ToggleButton(self, label=code, size=(34, 34))
                btn.SetForegroundColour(LIGHT_TEXT)
            btn.SetBackgroundColour(DARK_ALT)
            btn.SetToolTip(f"Toggle {_color_names.get(code, code)} color filter")
            btn.Bind(wx.EVT_TOGGLEBUTTON, self._on_filters_changed)
            _btn_ref = btn
            btn.Bind(
                wx.EVT_ENTER_WINDOW,
                lambda evt, b=_btn_ref: (
                    b.SetBackgroundColour((60, 68, 80)),
                    b.Refresh(),
                    evt.Skip(),
                ),
            )
            btn.Bind(
                wx.EVT_LEAVE_WINDOW,
                lambda evt, b=_btn_ref: (b.SetBackgroundColour(DARK_ALT), b.Refresh(), evt.Skip()),
            )
            color_controls.Add(btn, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_XS)
            self.color_checks[code] = btn
        color_col.Add(color_controls, 0)
        color_format_row.Add(color_col, 1, wx.RIGHT, PADDING_MD)

        format_col = wx.BoxSizer(wx.VERTICAL)
        format_label = wx.StaticText(self, label="Format")
        stylize_label(format_label, True)
        format_col.Add(format_label, 0, wx.BOTTOM, PADDING_XS)
        format_choice = wx.Choice(self, choices=["Any"] + list(FORMAT_OPTIONS))
        format_choice.SetSelection(0)
        stylize_choice(format_choice)
        format_choice.SetToolTip("Filter results to cards legal in the selected format")
        self.format_choice = format_choice
        format_choice.Bind(wx.EVT_CHOICE, self._on_filters_changed)
        format_col.Add(format_choice, 0, wx.EXPAND)
        color_format_row.Add(format_col, 0)

        sizer.Add(color_format_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_SM)

        # Clear button
        controls = wx.BoxSizer(wx.HORIZONTAL)
        clear_btn = wx.Button(self, label="Clear Filters")
        stylize_button(clear_btn)
        clear_btn.SetToolTip("Reset all search filters")
        clear_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_clear())
        controls.Add(clear_btn, 0, wx.RIGHT, PADDING_MD)

        # Radar toggle checkbox
        self.radar_cb = wx.CheckBox(self, label="Use Radar Filter")
        self.radar_cb.SetForegroundColour(LIGHT_TEXT)
        self.radar_cb.SetBackgroundColour(DARK_PANEL)
        self.radar_cb.SetToolTip("Show only cards that appear in the loaded radar archetype")
        self.radar_cb.Bind(wx.EVT_CHECKBOX, self._on_radar_toggle)
        controls.Add(self.radar_cb, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_MD)

        # Radar zone choice
        self.radar_zone_choice = wx.Choice(self, choices=["Both", "Mainboard", "Sideboard"])
        self.radar_zone_choice.SetSelection(0)
        stylize_choice(self.radar_zone_choice)
        self.radar_zone_choice.SetToolTip("Limit radar filtering to mainboard, sideboard, or both")
        self.radar_zone_choice.Enable(False)
        self.radar_zone_choice.Bind(wx.EVT_CHOICE, self._on_radar_zone_changed)
        controls.Add(self.radar_zone_choice, 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, PADDING_MD)

        # Open Radar button
        self.open_radar_btn = wx.Button(self, label="Open Radar...")
        stylize_button(self.open_radar_btn)
        self.open_radar_btn.SetToolTip("Open a radar to filter cards by archetype frequency")
        self.open_radar_btn.Bind(wx.EVT_BUTTON, self._on_open_radar)
        controls.Add(self.open_radar_btn, 0)

        controls.AddStretchSpacer(1)
        sizer.Add(controls, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)

        # Results list (virtual ListCtrl for handling large datasets)
        results = _SearchResultsView(self, style=0, mana_icons=self.mana_icons)
        # Column 0 is a hidden 0-width dummy that absorbs the Windows IMAGE_LIST_SMALL
        # indent (equal to the image-list item width).  Columns 1+ are sub-item columns
        # and are never indented by LVSIL_SMALL, so the Name cell is unindented.
        results.InsertColumn(0, "", width=0)
        results.InsertColumn(
            1, "Name", format=wx.LIST_FORMAT_LEFT, width=BUILDER_NAME_COL_DEFAULT_WIDTH
        )
        results.InsertColumn(2, "Mana Cost", width=BUILDER_MANA_CANVAS_WIDTH)
        results.SetBackgroundColour(DARK_ALT)
        results.SetForegroundColour(LIGHT_TEXT)
        results.Bind(wx.EVT_LIST_ITEM_SELECTED, self._on_result_item_selected)
        results.Bind(wx.EVT_LEFT_DOWN, self._on_results_left_down)
        results.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self._on_result_activated)
        results.Bind(wx.EVT_KEY_DOWN, self._on_result_key_down)
        sizer.Add(results, 1, wx.EXPAND | wx.LEFT, PADDING_MD)
        self.results_ctrl = results

        # Add to zone buttons
        add_btns_row = wx.BoxSizer(wx.HORIZONTAL)
        add_main_btn = wx.Button(self, label="+ Mainboard")
        stylize_button(add_main_btn)
        add_main_btn.SetToolTip("Add the selected card to the mainboard")
        add_main_btn.Enable(False)
        add_main_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_add_to_zone("main"))
        add_btns_row.Add(add_main_btn, 1, wx.RIGHT, PADDING_SM)
        self._add_main_btn = add_main_btn

        add_side_btn = wx.Button(self, label="+ Sideboard")
        stylize_button(add_side_btn)
        add_side_btn.SetToolTip("Add the selected card to the sideboard")
        add_side_btn.Enable(False)
        add_side_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._on_add_to_zone("side"))
        add_btns_row.Add(add_side_btn, 1)
        self._add_side_btn = add_side_btn

        sizer.Add(add_btns_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, PADDING_MD)

        # Status label
        status = wx.StaticText(self, label="Results update automatically as you type.")
        status.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(status, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, PADDING_MD)
        self.status_label = status

    def _on_back_clicked(self) -> None:
        """Handle back button click."""
        self._on_switch_to_research()

    def _on_result_item_selected(self, event: wx.ListEvent) -> None:
        """Handle result list item selection."""
        if not self.results_ctrl:
            return
        idx = event.GetIndex()
        if idx == wx.NOT_FOUND:
            return
        self._on_result_selected(idx)
        self._update_add_buttons()

    def _on_results_left_down(self, event: wx.MouseEvent) -> None:
        if not self.results_ctrl:
            event.Skip()
            return
        idx, _ = self.results_ctrl.HitTest(event.GetPosition())
        if idx != wx.NOT_FOUND and self.results_ctrl.IsSelected(idx):
            self.clear_result_selection()
            self._on_result_selected(None)
            return
        event.Skip()

    def _on_result_activated(self, event: wx.ListEvent) -> None:
        """Handle double-click or Enter on search result."""
        idx = event.GetIndex()
        self._add_result_by_index(idx)

    def _on_result_key_down(self, event: wx.KeyEvent) -> None:
        """Handle + key in search results to add to active zone."""
        if event.GetKeyCode() == ord("+") and not event.ControlDown():
            if self.results_ctrl:
                selected = self.results_ctrl.GetFirstSelected()
                if selected != wx.NOT_FOUND:
                    self._add_result_by_index(selected)
                    return
        event.Skip()

    def _add_result_by_index(self, idx: int) -> None:
        """Add the search result at the given index to the active zone."""
        card = self.get_result_at_index(idx)
        if card and self._on_add_to_active_zone:
            name = card.get("name")
            if name:
                self._on_add_to_active_zone(name)

    def _on_add_to_zone(self, zone: str) -> None:
        """Handle add-to-zone button click."""
        card = self.get_selected_result()
        if not card:
            return
        name = card.get("name")
        if not name:
            return
        if zone == "main" and self._on_add_to_main:
            self._on_add_to_main(name)
        elif zone == "side" and self._on_add_to_side:
            self._on_add_to_side(name)

    def _update_add_buttons(self) -> None:
        """Enable or disable add buttons based on current selection."""
        has_selection = self.get_selected_result() is not None
        if self._add_main_btn:
            self._add_main_btn.Enable(has_selection and bool(self._on_add_to_main))
        if self._add_side_btn:
            self._add_side_btn.Enable(has_selection and bool(self._on_add_to_side))

    def _append_mana_symbol(self, token: str) -> None:
        """Append a mana symbol to the mana cost field."""
        ctrl = self.inputs.get("mana")
        if not ctrl:
            return
        symbol = token.strip().upper()
        if not symbol:
            return
        text = symbol if symbol.startswith("{") else f"{{{symbol}}}"
        ctrl.ChangeValue(ctrl.GetValue() + text)
        ctrl.SetFocus()
        self._schedule_search()

    def get_filters(self) -> dict[str, Any]:
        """Get all current filter values."""
        filters = {key: ctrl.GetValue().strip() for key, ctrl in self.inputs.items()}
        filters["mana_exact"] = self.mana_exact_cb.IsChecked() if self.mana_exact_cb else False
        filters["text_mode"] = (
            "any" if self.text_mode_choice and self.text_mode_choice.GetSelection() == 1 else "all"
        )
        filters["mv_comparator"] = (
            self.mv_comparator.GetStringSelection() if self.mv_comparator else "Any"
        )
        mv_value_text = self.mv_value.GetValue().strip() if self.mv_value else ""
        filters["mv_value"] = mv_value_text
        filters["formats"] = (
            [self.format_choice.GetStringSelection().lower()]
            if self.format_choice and self.format_choice.GetSelection() > 0
            else []
        )
        filters["color_mode"] = (
            self.color_mode_choice.GetStringSelection() if self.color_mode_choice else "Any"
        )
        filters["selected_colors"] = [
            code for code, btn in self.color_checks.items() if btn.GetValue()
        ]

        # Add radar filter if enabled
        filters["radar_enabled"] = self.radar_enabled
        if self.radar_enabled and self.active_radar:
            from services.radar_service import get_radar_service

            radar_service = get_radar_service()
            filters["radar_cards"] = radar_service.get_radar_card_names(
                self.active_radar, self.radar_zone
            )
        else:
            filters["radar_cards"] = set()

        return filters

    def clear_filters(self) -> None:
        """Clear all filter controls."""
        for ctrl in self.inputs.values():
            ctrl.ChangeValue("")
        self.results_cache = []
        if self.results_ctrl:
            self.results_ctrl.SetData([])

        if self.status_label:
            self.status_label.SetLabel("Filters cleared.")
        if self.mana_exact_cb:
            self.mana_exact_cb.SetValue(False)
        if self.text_mode_choice:
            self.text_mode_choice.SetSelection(0)
        if self.mv_comparator:
            self.mv_comparator.SetSelection(0)
        if self.mv_value:
            self.mv_value.ChangeValue("")
        if self.format_choice:
            self.format_choice.SetSelection(0)
        if self.color_mode_choice:
            self.color_mode_choice.SetSelection(0)
        for cb in self.color_checks.values():
            cb.SetValue(False)

        # Clear radar filter
        self.radar_enabled = False
        self.active_radar = None
        if hasattr(self, "radar_cb"):
            self.radar_cb.SetValue(False)
            self.radar_zone_choice.Enable(False)
        self._schedule_search()

    def update_results(self, results: list[dict[str, Any]]) -> None:
        """Update the results list with search results."""
        self.results_cache = results
        if not self.results_ctrl:
            return
        self.results_ctrl.SetData(results)
        if self.status_label:
            count = len(results)
            self.status_label.SetLabel(f"Showing {count} card{'s' if count != 1 else ''}.")

    def get_result_at_index(self, idx: int) -> dict[str, Any] | None:
        """Get the result card data at the given index."""
        if idx < 0 or idx >= len(self.results_cache):
            return None
        return self.results_cache[idx]

    def get_selected_result(self) -> dict[str, Any] | None:
        """Return the currently selected search result, if any."""
        if not self.results_ctrl:
            return None
        selected = self.results_ctrl.GetFirstSelected()
        return self.get_result_at_index(selected) if selected != wx.NOT_FOUND else None

    def clear_result_selection(self) -> None:
        if not self.results_ctrl:
            return
        selected = self.results_ctrl.GetFirstSelected()
        if selected != wx.NOT_FOUND:
            self.results_ctrl.Select(selected, on=0)
        self._update_add_buttons()

    def _on_search(self) -> None:
        """Trigger search callback."""
        self._on_search_callback()

    def _on_filters_changed(self, event: wx.Event | None = None) -> None:
        """Handle any filter change by scheduling a search."""
        self._schedule_search()
        if event:
            event.Skip()

    def _on_clear(self) -> None:
        """Handle clear button click."""
        self._on_clear_callback()

    def _on_result_selected(self, idx: int | None) -> None:
        """Handle result list item selection."""
        self._on_result_selected_callback(idx)

    def _schedule_search(self) -> None:
        """Debounce search execution when filters change."""
        if not self._search_timer:
            return
        if self._search_timer.IsRunning():
            self._search_timer.Stop()
        self._search_timer.StartOnce(BUILDER_SEARCH_DEBOUNCE_MS)

    def _on_search_timer(self, _event: wx.TimerEvent) -> None:
        """Run the search after the debounce timer fires."""
        self._on_search()

    # ============= Radar Integration =============

    def _on_radar_toggle(self, event: wx.Event) -> None:
        """Handle radar filter checkbox toggle."""
        self.radar_enabled = self.radar_cb.IsChecked()
        self.radar_zone_choice.Enable(self.radar_enabled)

        if self.radar_enabled and not self.active_radar:
            wx.MessageBox(
                "Please open a radar using the 'Open Radar...' button.",
                "No Radar Loaded",
                wx.OK | wx.ICON_INFORMATION,
            )
            self.radar_cb.SetValue(False)
            self.radar_enabled = False
            self.radar_zone_choice.Enable(False)
        self._schedule_search()

    def _on_radar_zone_changed(self, event: wx.Event) -> None:
        """Handle radar zone selection change."""
        selection = self.radar_zone_choice.GetSelection()
        zone_map = {0: "both", 1: "mainboard", 2: "sideboard"}
        self.radar_zone = zone_map.get(selection, "both")
        self._schedule_search()

    def _on_open_radar(self, event: wx.Event) -> None:
        """Handle open radar button click."""
        if self._on_open_radar_dialog:
            radar = self._on_open_radar_dialog()
            if radar:
                self.set_active_radar(radar)

    def set_active_radar(self, radar: RadarData) -> None:
        """
        Set the active radar for filtering.

        Args:
            radar: RadarData to use for filtering
        """
        self.active_radar = radar
        self.radar_enabled = True
        self.radar_cb.SetValue(True)
        self.radar_zone_choice.Enable(True)

        if self.status_label:
            self.status_label.SetLabel(
                f"Radar active: {radar.archetype_name} "
                f"({len(radar.mainboard_cards)} MB, {len(radar.sideboard_cards)} SB cards)"
            )
        self._schedule_search()
