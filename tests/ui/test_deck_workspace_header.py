"""F3 — the deck workspace header says what its controls do.

``⋯`` named neither its function nor its state, ``Art`` named a view mode that
does not exist (phase 4: ``VIEW_MODES`` is grid/table/pile), and both sat inside
the run of view-toggle chips. What these pin is the part that is invisible until
someone narrows the window in Portuguese: the row grew ~100px wider doing it, and
only the count label is allowed to give way.
"""

from __future__ import annotations

import pytest
import wx

from widgets.panels.card_table_panel.sorting import PILE_SORT_COLOR, PILE_SORT_MV


def _header_sizer(panel: wx.Window) -> wx.Sizer:
    """The row the count label sits on.

    Phase 8 put the header in a two-row stack: the count label always occupies
    the top row, and the view controls sit beside it there or drop to the row
    below when the panel is too narrow for both (see
    ``CardTablePanelToolbarMixin._reflow_header``). ``outer.GetItem(0)`` is now
    that stack rather than a single row.
    """
    outer = panel.GetSizer()
    return outer.GetItem(0).GetSizer().GetItem(0).GetSizer()


def _header_windows(panel: wx.Window) -> list[wx.Window]:
    """Every control in the header, in reading order, whichever row it is on."""
    stack = panel.GetSizer().GetItem(0).GetSizer()
    windows: list[wx.Window] = []
    for row in stack.GetChildren():
        row_sizer = row.GetSizer()
        if row_sizer is None:
            continue
        for item in row_sizer.GetChildren():
            if item.GetWindow() is not None:
                windows.append(item.GetWindow())
            elif item.GetSizer() is not None:
                windows.extend(
                    i.GetWindow() for i in item.GetSizer().GetChildren() if i.GetWindow()
                )
    return windows


@pytest.mark.usefixtures("wx_app")
def test_the_pile_sort_button_is_labelled_with_the_current_grouping_key(
    deck_selector_factory,
) -> None:
    frame = deck_selector_factory()
    try:
        table = frame.main_table
        table.set_pile_sort(PILE_SORT_MV, persist=False)
        assert table._t("tabs.view.pile_sort.mv") in table.pile_sort_button.GetLabel()
        table.set_pile_sort(PILE_SORT_COLOR, persist=False)
        assert table._t("tabs.view.pile_sort.color") in table.pile_sort_button.GetLabel()
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_menu_buttons_sit_after_the_divider_not_inside_the_toggle_group(
    deck_selector_factory,
) -> None:
    frame = deck_selector_factory()
    try:
        table = frame.main_table
        windows = _header_windows(table)
        divider_index = windows.index(table.header_divider)
        for chip in table._view_mode_buttons.values():
            assert windows.index(chip) < divider_index
        assert windows.index(table.pile_sort_button) > divider_index
        if table.printing_button is not None:
            assert windows.index(table.printing_button) > divider_index
        # ...and the caption naming the group is in front of the chips.
        assert windows.index(table.view_label) < min(
            windows.index(chip) for chip in table._view_mode_buttons.values()
        )
    finally:
        frame.Destroy()


@pytest.mark.usefixtures("wx_app")
def test_the_count_label_is_the_row_member_that_gives_way(deck_selector_factory) -> None:
    """A row of fixed controls overflows silently and clips only its *last* item.

    Measured in pt-BR at the 1200px floor: the row wanted 551px in a 506px panel,
    seven controls rendered at exactly their minimums and the printing button was
    painted 14px wide. ``AddStretchSpacer`` cannot give anything back once the
    slack is gone, so the count label carries the proportion instead -- and needs
    ``ST_ELLIPSIZE_END`` from the **constructor** plus ``ST_NO_AUTORESIZE`` for
    that to be visible rather than merely true.

    Phase 8 found that this only postpones the failure -- once the label is at
    its floor the deficit moves back onto the buttons, and the row's real
    minimum is view-mode and locale dependent -- so the controls now wrap to a
    second line instead. The count label is still the flexible member of the row
    it is on, which is what this pins.
    """
    frame = deck_selector_factory()
    try:
        table = frame.main_table
        header = _header_sizer(table)
        item = next(i for i in header.GetChildren() if i.GetWindow() is table.count_label)
        assert item.GetProportion() == 1
        assert not any(i.IsSpacer() and i.GetProportion() for i in header.GetChildren())
        style = table.count_label.GetWindowStyleFlag()
        assert style & wx.ST_ELLIPSIZE_END
        assert style & wx.ST_NO_AUTORESIZE
        assert table.count_label.GetMinSize().GetWidth() > 0
    finally:
        frame.Destroy()
