"""Hypergeometric calculator panel construction (left-top of the overlay)."""

from __future__ import annotations

import wx

from utils.constants import (
    CALC_ACTION_BUTTON_SPACING,
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
    DARK_PANEL,
    LIGHT_TEXT,
)
from widgets.stylize import apply_type_level, stylize_button, stylize_spinctrl


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
        apply_type_level(title, "heading")
        calc_sizer.Add(title, 0, wx.ALL, CALC_SECTION_PADDING)

        self._build_calculator_inputs(calc_sizer)
        self._build_calculator_button_rows(calc_sizer)

        # Bind Enter key on spin controls, and theme them: left alone these are
        # four solid-white fields on the darkest panel in the app (issue #962).
        for spin in [
            self.spin_deck_size,
            self.spin_copies,
            self.spin_drawn,
            self.spin_target,
        ]:
            stylize_spinctrl(spin)
            spin.Bind(wx.EVT_TEXT_ENTER, self._on_calculate)

        # Result display
        self.calc_result_label = wx.StaticText(self.calc_panel, label="")
        self.calc_result_label.SetForegroundColour(LIGHT_TEXT)
        calc_sizer.Add(self.calc_result_label, 0, wx.ALL, CALC_SECTION_PADDING)

    def _build_calculator_inputs(self, calc_sizer: wx.Sizer) -> None:
        grid = wx.FlexGridSizer(CALC_GRID_ROWS, CALC_GRID_COLS, CALC_GRID_VGAP, CALC_GRID_HGAP)
        calc_sizer.Add(grid, 0, wx.ALL | wx.EXPAND, CALC_SECTION_PADDING)

        # Deck Size
        lbl_deck = wx.StaticText(self.calc_panel, label="Deck Size")
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
        lbl_copies = wx.StaticText(self.calc_panel, label="Copies in Deck")
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
        lbl_drawn = wx.StaticText(self.calc_panel, label="Cards Drawn")
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
        lbl_target = wx.StaticText(self.calc_panel, label="Target Copies")
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
        r"""The six preset/action buttons, as one 3x2 grid rather than three rows.

        A2: these were three independent ``wx.BoxSizer``\ s, each centring its own
        pair between two stretch spacers, and rows 1-2 used
        ``CALC_PRESET_BUTTON_SPACING`` while row 3 used
        ``CALC_ACTION_BUTTON_SPACING``. So the third row was 4px wider than the
        two above it and, being centred independently, sat 2px left and 2px right
        of them -- a ragged edge on both sides of a six-button block.

        One ``wx.GridSizer`` with ``wx.EXPAND`` gives all six cells identical
        width by construction, which is also why the fixed
        ``CALC_PRESET_BUTTON_WIDTH`` is now a *minimum* rather than the size: the
        grid stretches the columns to the panel, so the block lines up with the
        spin-control grid above it instead of floating inside it.
        """
        btn_size = (CALC_PRESET_BUTTON_WIDTH, CALC_PRESET_BUTTON_HEIGHT)
        grid = wx.GridSizer(3, 2, CALC_GRID_VGAP, CALC_ACTION_BUTTON_SPACING)

        def _make_preset_btn(label: str, deck: int, drawn: int) -> wx.Button:
            btn = wx.Button(self.calc_panel, label=label, size=btn_size)
            stylize_button(btn, kind="ghost")
            btn.Bind(wx.EVT_BUTTON, lambda evt, d=deck, n=drawn: self._apply_preset(d, n))
            return btn

        grid.Add(
            _make_preset_btn("Open 60", CALC_PRESET_OPEN_60_DECK, CALC_PRESET_OPEN_60_DRAWN),
            0,
            wx.EXPAND,
        )
        grid.Add(
            _make_preset_btn("Open 40", CALC_PRESET_OPEN_40_DECK, CALC_PRESET_OPEN_40_DRAWN),
            0,
            wx.EXPAND,
        )
        grid.Add(
            _make_preset_btn("T3 Play", CALC_PRESET_T3_PLAY_DECK, CALC_PRESET_T3_PLAY_DRAWN),
            0,
            wx.EXPAND,
        )
        grid.Add(
            _make_preset_btn("T3 Draw", CALC_PRESET_T3_DRAW_DECK, CALC_PRESET_T3_DRAW_DRAWN),
            0,
            wx.EXPAND,
        )

        # Retires CALC_BUTTON_GREEN. The old pairing measured 5.49:1; SUCCESS_FILL
        # with SUCCESS_ON_FILL measures 7.25:1, so this is not a regression.
        calc_btn = wx.Button(self.calc_panel, label="Calculate", size=btn_size)
        stylize_button(calc_btn, kind="success")
        calc_btn.Bind(wx.EVT_BUTTON, self._on_calculate)
        grid.Add(calc_btn, 0, wx.EXPAND)

        clear_btn = wx.Button(self.calc_panel, label="Clear", size=btn_size)
        stylize_button(clear_btn, kind="secondary")
        clear_btn.Bind(wx.EVT_BUTTON, self._on_clear_calculator)
        grid.Add(clear_btn, 0, wx.EXPAND)

        calc_sizer.Add(grid, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, CALC_SECTION_PADDING)

    def _fit_left_splitter(self) -> None:
        calc_best = self.calc_panel.GetBestSize()
        sash_h = calc_best.GetHeight()
        splitter_w = calc_best.GetWidth()
        self._left_splitter.SetMinSize(wx.Size(splitter_w, -1))
        self._left_splitter.SetSashPosition(sash_h)
        self.Layout()
