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
from widgets.spin_ctrl import DarkSpinCtrl
from widgets.stylize import apply_type_level, stylize_button


class CalculatorPanelBuilderMixin:
    """Builds the hypergeometric calculator panel and its splitter-fitting helper.

    Kept as a mixin (no ``__init__``) so :class:`MTGOpponentDeckSpy` remains the
    single source of truth for instance-state initialization.
    """

    calc_panel: wx.Panel
    spin_deck_size: DarkSpinCtrl
    spin_copies: DarkSpinCtrl
    spin_drawn: DarkSpinCtrl
    spin_target: DarkSpinCtrl
    calc_result_label: wx.StaticText
    _left_splitter: wx.SplitterWindow
    #: Sash position that shows the calculator whole; ``None`` until fitted.
    _preferred_sash: int | None = None
    #: Set once the user drags the sash, after which their choice is kept.
    _sash_user_set: bool = False
    #: True while this code moves the sash, so the move is not read as a drag.
    _applying_sash: bool = False

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

        # Enter calculates. The binding predates this redesign and had never
        # fired: wxMSW only forwards Enter to a wx.SpinCtrl's buddy Edit when the
        # control carries wx.TE_PROCESS_ENTER, and this site never passed it --
        # verified live against the native control, where Enter left the result
        # label empty. DarkSpinCtrl builds its field with the style, so it works.
        # Theming is no longer a call site's job either: the control is dark by
        # construction, arrows included (widgets/spin_ctrl.py).
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
        lbl_deck = wx.StaticText(self.calc_panel, label="Deck Size")
        lbl_deck.SetForegroundColour(LIGHT_TEXT)
        self.spin_deck_size = DarkSpinCtrl(
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
        self.spin_copies = DarkSpinCtrl(
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
        self.spin_drawn = DarkSpinCtrl(
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
        self.spin_target = DarkSpinCtrl(
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

        # Left-aligned at its natural width rather than stretched across the
        # pane. A2 gave the six cells one identical width, which wx.GridSizer
        # guarantees on its own; stretching them was only ever harmless while
        # this column was pinned to the calculator's fitted width. Now that the
        # column takes a share of the window, EXPAND turned six small buttons
        # into six half-pane slabs. The stretch spacer keeps the block's left
        # edge flush with the spin-control grid above it at any pane width.
        button_row = wx.BoxSizer(wx.HORIZONTAL)
        button_row.Add(grid, 0)
        button_row.AddStretchSpacer(1)
        calc_sizer.Add(
            button_row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, CALC_SECTION_PADDING
        )

    def _fit_left_splitter(self) -> None:
        calc_best = self.calc_panel.GetBestSize()
        sash_h = calc_best.GetHeight()
        splitter_w = calc_best.GetWidth()
        self._preferred_sash = sash_h
        self._left_splitter.SetMinSize(wx.Size(splitter_w, -1))
        self._left_splitter.SetSashPosition(sash_h)
        # CHANGING, not CHANGED: wx sends CHANGED for its own resize-time
        # clamping too, so binding that marked every window resize as a user
        # drag and permanently disabled the restore below. CHANGING is only
        # sent from the live-drag mouse handler.
        self._left_splitter.Bind(wx.EVT_SPLITTER_SASH_POS_CHANGING, self._on_left_sash_dragged)
        self.Layout()

    def _on_left_sash_dragged(self, event: wx.SplitterEvent) -> None:
        """A dragged sash is the user's choice; stop re-fitting it for them."""
        event.Skip()
        if not self._applying_sash:
            self._sash_user_set = True

    def _restore_left_sash(self) -> None:
        """Put the sash back where the calculator fits after a window resize.

        Shrinking the window forces wx to clamp the sash up so the bottom pane
        keeps its minimum; growing the window again does not push it back, so
        the calculator stayed cut off mid-control until someone dragged the sash
        by hand. Re-applying the fitted position (which wx clamps again when
        there is no room) restores it, unless the user has moved it themselves.
        """
        if self._sash_user_set or self._preferred_sash is None:
            return
        # Deferred via CallAfter, so the frame may already be on its way out.
        if not self._is_widget_ok(getattr(self, "_left_splitter", None)):
            return
        if not self._left_splitter.IsSplit():
            return
        if self._left_splitter.GetSashPosition() == self._preferred_sash:
            return
        self._applying_sash = True
        try:
            self._left_splitter.SetSashPosition(self._preferred_sash)
        finally:
            self._applying_sash = False
