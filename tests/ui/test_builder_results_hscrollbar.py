"""The builder's card-search list must never show a horizontal scrollbar it cannot use.

The defect this encodes
-----------------------
Reported as "a horizontal scrollbar appears sporadically in the card search, and
it serves no purpose". It is not sporadic. ``_SearchResultsView`` fits its Name
column to ``client width - the fixed columns``, so the columns summed to
**exactly** the client width, and it did that fit only from ``EVT_SIZE``.

Two client-width changes arrive without an ``EVT_SIZE`` that can beat them:

1. ``SetItemCount`` crossing the row count that needs a **vertical** scrollbar.
   That bar is non-client area, so the window never resizes and wxMSW sends no
   size event -- but ``GetClientSize().width`` drops by its width, and columns
   fitted to the old width now overflow by exactly that much.
2. The empty-state swap in ``update_results``, which resizes the list itself.

Either way comctl32 raises the horizontal scrollbar, and the follow-up
``SetColumnWidth`` -- which runs from *inside* comctl32's own resize -- does not
get re-evaluated. The bar stays up over content that fits, taking 17px of list
height with it, until something else happens to change a column width.

What is asserted
----------------
The mechanism, not the pixels: the columns must sum to strictly less than the
client width, and ``WS_HSCROLL`` must be off. ``has_horizontal_scrollbar`` reads
the HWND style bit because there is no wx-level answer -- ``HasScrollbar``
answers from the wx style (always ``False`` here) and ``GetScrollRange`` reports
the content width whether the bar is up or not. Both measured; see
``docs/WXMSW_BEHAVIOUR.md``.

The frame is shown and raised deliberately. An occluded or never-shown window
does not lay its native control out the way a visible one does, and a guard that
passes against the unfixed code because nothing ever painted is worse than none.
"""

from __future__ import annotations

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from utils.constants import BUILDER_MANA_CANVAS_WIDTH, BUILDER_NAME_COL_DEFAULT_WIDTH
from widgets.native_dark import has_horizontal_scrollbar
from widgets.panels.deck_builder_panel.frame.search_results_view import _SearchResultsView

#: Enough rows that the list needs a vertical scrollbar at any test size.
_MANY = 500


def _cards(count: int) -> list[dict[str, object]]:
    return [{"name": f"Test Card {i:04d}", "mana_cost": "{1}{R}"} for i in range(count)]


@pytest.fixture(name="results_view")
def fixture_results_view(wx_app):
    """A realized, visible results list built exactly the way the builder builds it."""
    frame = wx.Frame(None, title="results list guard", size=(600, 420))
    view = _SearchResultsView(frame, style=0, mana_icons=None)
    view.InsertColumn(0, "", width=0)
    view.InsertColumn(1, "Name", format=wx.LIST_FORMAT_LEFT, width=BUILDER_NAME_COL_DEFAULT_WIDTH)
    view.InsertColumn(2, "Mana Cost", width=BUILDER_MANA_CANVAS_WIDTH)
    sizer = wx.BoxSizer(wx.VERTICAL)
    sizer.Add(view, 1, wx.EXPAND)
    frame.SetSizer(sizer)
    frame.Show()
    frame.Raise()
    frame.Update()
    pump_ui_events(wx_app)
    try:
        yield view
    finally:
        frame.Hide()
        frame.Destroy()
        pump_ui_events(wx_app)


def _columns_total(view: _SearchResultsView) -> int:
    return sum(view.GetColumnWidth(col) for col in range(view.GetColumnCount()))


def _assert_no_spurious_bar(view: _SearchResultsView, wx_app, context: str) -> None:
    pump_ui_events(wx_app)
    total, client = _columns_total(view), view.GetClientSize().width
    # The symptom first, so a failure names what the user sees.
    assert not has_horizontal_scrollbar(view), (
        f"{context}: WS_HSCROLL is set on the results list while its columns "
        f"({total}px) fit inside its {client}px client -- a scrollbar with nothing "
        "to scroll, costing 17px of list height."
    )
    # Then the state that keeps producing it: an exact fit is one client-width
    # change away from the bar above, and wxMSW will not take that bar back down.
    assert total < client, (
        f"{context}: the columns sum to {total} in a {client}px client, leaving no "
        "slack. The next client-width change -- a vertical scrollbar appearing, the "
        "empty-state swap resizing the list -- puts up a horizontal scrollbar that "
        "the follow-up column fit cannot clear."
    )


def test_no_hscrollbar_when_the_vertical_one_appears(results_view, wx_app) -> None:
    """The reported trigger: a search whose results first need a vertical scrollbar.

    The list is laid out while it is short (no vertical bar), then filled. The
    vertical bar takes its width out of the client with no size event, and the
    columns -- fitted to the wider client -- overflow.
    """
    results_view.SetData(_cards(1))
    _assert_no_spurious_bar(results_view, wx_app, "one row, no vertical scrollbar")

    results_view.SetData(_cards(_MANY))
    _assert_no_spurious_bar(results_view, wx_app, f"{_MANY} rows, vertical scrollbar appeared")


def test_no_hscrollbar_after_the_row_count_falls_back(results_view, wx_app) -> None:
    """And back the other way, repeatedly -- this is what "sporadic" was."""
    for cycle in range(3):
        results_view.SetData(_cards(_MANY))
        _assert_no_spurious_bar(results_view, wx_app, f"cycle {cycle}: long result set")
        results_view.SetData(_cards(0))
        _assert_no_spurious_bar(results_view, wx_app, f"cycle {cycle}: empty result set")
        results_view.SetData(_cards(2))
        _assert_no_spurious_bar(results_view, wx_app, f"cycle {cycle}: short result set")


def test_no_hscrollbar_after_the_list_is_narrowed(results_view, wx_app) -> None:
    """The other trigger: the empty-state swap resizes the list under the columns.

    comctl32 raises the bar during that resize, before ``EVT_SIZE`` can narrow the
    columns, and the width written from inside the resize does not take it down
    again. Narrowing the control directly is the same event in miniature.
    """
    results_view.SetData(_cards(3))
    _assert_no_spurious_bar(results_view, wx_app, "before narrowing")

    for width in (520, 460, 400, 640):
        results_view.SetSize((width, results_view.GetSize().height))
        results_view.GetParent().Update()
        _assert_no_spurious_bar(results_view, wx_app, f"narrowed to {width}px")
