"""Hypergeometric calculator panel construction (left-top of the overlay)."""

from __future__ import annotations

import wx

from utils.constants import (
    CALC_ACTION_BUTTON_SPACING,
    CALC_BUTTON_GREEN,
    CALC_COPIES_DEFAULT,
    CALC_COPIES_MAX,
    CALC_DECK_SIZE_DEFAULT,
    CALC_DECK_SIZE_MAX,
    CALC_DECK_SIZE_MIN,
    CALC_DRAWN_DEFAULT,
    CALC_GRID_COLS,
    CALC_GRID_HGAP,
    CALC_GRID_ROWS,
    CALC_GRID_VGAP,
    CALC_PRESET_BUTTON_HEIGHT,
    CALC_PRESET_BUTTON_SPACING,
    CALC_PRESET_BUTTON_WIDTH,
    CALC_PRESET_OPEN_40_DECK,
    CALC_PRESET_OPEN_40_DRAWN,
    CALC_PRESET_OPEN_60_DECK,
    CALC_PRESET_OPEN_60_DRAWN,
    CALC_PRESET_T3_DRAW_DECK,
    CALC_PRESET_T3_DRAW_DRAWN,
    CALC_PRESET_T3_PLAY_DECK,
    CALC_PRESET_T3_PLAY_DRAWN,
    CALC_SECTION_PADDING,
    CALC_SPIN_WIDTH,
    CALC_TARGET_DEFAULT,
    DARK_BG,
    DARK_PANEL,
    LIGHT_TEXT,
)


class CalculatorPanelBuilderMixin:
    """Builds the hypergeometric calculator panel and its splitter-fitting helper.

    Kept as a mixin (no ``__init__``) so :class:`MTGOpponentDeckSpy` remains the
    single source of truth for instance-state initialization.
    """

    calc_panel: wx.Panel
    spin_deck_size: wx.SpinCtrl
    spin_copies: wx.SpinCtrl
    spin_drawn: wx.SpinCtrl
    spin_target: wx.SpinCtrl
    calc_result_label: wx.StaticText
    _left_splitter: wx.SplitterWindow

    def _build_calculator_panel(self, parent: wx.Window) -> None:
        self.calc_panel = wx.Panel(parent)
        self.calc_panel.SetBackgroundColour(DARK_PANEL)

        calc_sizer = wx.BoxSizer(wx.VERTICAL)
        self.calc_panel.SetSizer(calc_sizer)

        # Title
        title = wx.StaticText(self.calc_panel, label="Hypergeometric Calculator")
        title.SetForegroundColour(LIGHT_TEXT)
        title_font = title.GetFont()
        title_font.MakeBold()
        title.SetFont(title_font)
        calc_sizer.Add(title, 0, wx.ALL, CALC_SECTION_PADDING)

        self._build_calculator_inputs(calc_sizer)
        self._build_calculator_button_rows(calc_sizer)

        # Bind Enter key on spin controls
        for spin in [
            self.spin_deck_size,
            self.spin_copies,
            self.spin_drawn,
            self.spin_target,
        ]:
            spin.Bind(wx.EVT_TEXT_ENTER, self._on_calculate)

        # Result display
        self.calc_result_label = wx.StaticText(self.calc_panel, label="")
        self.calc_result_label.SetForegroundColour(LIGHT_TEXT)
        calc_sizer.Add(self.calc_result_label, 0, wx.ALL, CALC_SECTION_PADDING)

    def _build_calculator_inputs(self, calc_sizer: wx.Sizer) -> None:
        grid = wx.FlexGridSizer(CALC_GRID_ROWS, CALC_GRID_COLS, CALC_GRID_VGAP, CALC_GRID_HGAP)
        calc_sizer.Add(grid, 0, wx.ALL | wx.EXPAND, CALC_SECTION_PADDING)

        # Deck Size
        lbl_deck = wx.StaticText(self.calc_panel, label="Deck Size:")
        lbl_deck.SetForegroundColour(LIGHT_TEXT)
        self.spin_deck_size = wx.SpinCtrl(
            self.calc_panel,
            min=CALC_DECK_SIZE_MIN,
            max=CALC_DECK_SIZE_MAX,
            initial=CALC_DECK_SIZE_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_deck_size.SetToolTip("Total cards in deck (N)")
        grid.Add(lbl_deck, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_deck_size, 0)

        # Copies in Deck
        lbl_copies = wx.StaticText(self.calc_panel, label="Copies in Deck:")
        lbl_copies.SetForegroundColour(LIGHT_TEXT)
        self.spin_copies = wx.SpinCtrl(
            self.calc_panel,
            min=0,
            max=CALC_COPIES_MAX,
            initial=CALC_COPIES_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_copies.SetToolTip("Number of target cards in deck (K)")
        grid.Add(lbl_copies, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_copies, 0)

        # Cards Drawn
        lbl_drawn = wx.StaticText(self.calc_panel, label="Cards Drawn:")
        lbl_drawn.SetForegroundColour(LIGHT_TEXT)
        self.spin_drawn = wx.SpinCtrl(
            self.calc_panel,
            min=0,
            max=CALC_COPIES_MAX,
            initial=CALC_DRAWN_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_drawn.SetToolTip("Number of cards drawn (n)")
        grid.Add(lbl_drawn, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_drawn, 0)

        # Target Copies
        lbl_target = wx.StaticText(self.calc_panel, label="Target Copies:")
        lbl_target.SetForegroundColour(LIGHT_TEXT)
        self.spin_target = wx.SpinCtrl(
            self.calc_panel,
            min=0,
            max=CALC_COPIES_MAX,
            initial=CALC_TARGET_DEFAULT,
            size=(CALC_SPIN_WIDTH, -1),
        )
        self.spin_target.SetToolTip("Desired number of target cards (k)")
        grid.Add(lbl_target, 0, wx.ALIGN_CENTER_VERTICAL)
        grid.Add(self.spin_target, 0)

    def _build_calculator_button_rows(self, calc_sizer: wx.Sizer) -> None:
        # Button rows: Open 60 / Open 40 | T3 Play / T3 Draw | Calculate / Clear
        btn_size = (CALC_PRESET_BUTTON_WIDTH, CALC_PRESET_BUTTON_HEIGHT)

        def _make_preset_btn(label: str, deck: int, drawn: int) -> wx.Button:
            btn = wx.Button(self.calc_panel, label=label, size=btn_size)
            btn.SetBackgroundColour(DARK_BG)
            btn.SetForegroundColour(LIGHT_TEXT)
            btn.Bind(wx.EVT_BUTTON, lambda evt, d=deck, n=drawn: self._apply_preset(d, n))
            return btn

        def _centered_row(left: wx.Button, right: wx.Button, gap: int) -> wx.BoxSizer:
            row = wx.BoxSizer(wx.HORIZONTAL)
            row.AddStretchSpacer(1)
            row.Add(left, 0, wx.RIGHT, gap)
            row.Add(right, 0)
            row.AddStretchSpacer(1)
            return row

        # Row 1: Open 60 | Open 40
        open60 = _make_preset_btn("Open 60", CALC_PRESET_OPEN_60_DECK, CALC_PRESET_OPEN_60_DRAWN)
        open40 = _make_preset_btn("Open 40", CALC_PRESET_OPEN_40_DECK, CALC_PRESET_OPEN_40_DRAWN)
        calc_sizer.Add(
            _centered_row(open60, open40, CALC_PRESET_BUTTON_SPACING),
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            CALC_SECTION_PADDING,
        )

        # Row 2: T3 Play | T3 Draw
        t3play = _make_preset_btn("T3 Play", CALC_PRESET_T3_PLAY_DECK, CALC_PRESET_T3_PLAY_DRAWN)
        t3draw = _make_preset_btn("T3 Draw", CALC_PRESET_T3_DRAW_DECK, CALC_PRESET_T3_DRAW_DRAWN)
        calc_sizer.Add(
            _centered_row(t3play, t3draw, CALC_PRESET_BUTTON_SPACING),
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            CALC_SECTION_PADDING,
        )

        # Row 3: Calculate | Clear
        calc_btn = wx.Button(self.calc_panel, label="Calculate", size=btn_size)
        calc_btn.SetBackgroundColour(CALC_BUTTON_GREEN)
        calc_btn.SetForegroundColour(LIGHT_TEXT)
        font = calc_btn.GetFont()
        font.MakeBold()
        calc_btn.SetFont(font)
        calc_btn.Bind(wx.EVT_BUTTON, self._on_calculate)

        clear_btn = wx.Button(self.calc_panel, label="Clear", size=btn_size)
        clear_btn.SetBackgroundColour(DARK_BG)
        clear_btn.SetForegroundColour(LIGHT_TEXT)
        clear_btn.Bind(wx.EVT_BUTTON, self._on_clear_calculator)

        calc_sizer.Add(
            _centered_row(calc_btn, clear_btn, CALC_ACTION_BUTTON_SPACING),
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            CALC_SECTION_PADDING,
        )

    def _fit_left_splitter(self) -> None:
        calc_best = self.calc_panel.GetBestSize()
        sash_h = calc_best.GetHeight()
        splitter_w = calc_best.GetWidth()
        self._left_splitter.SetMinSize(wx.Size(splitter_w, -1))
        self._left_splitter.SetSashPosition(sash_h)
        self.Layout()
