"""Every string in the Match History window has a theme text colour.

The window shipped with three controls that were given a background and never a
foreground, so they painted in wxMSW's default **#000000** on a dark surface:
the match tree (1.53:1 on ``SURFACE_ALT``), its column header labels (1.29:1 on
the OS dark header strip) and the two date-filter captions (1.53:1 on
``SURFACE_PANEL``). A user reported it as "the black font is hard to see".

This is a live-tree audit in the spirit of ``tests/ui/test_live_widget_audit.py``
rather than a check on the styling helper: ``tests/test_stylize.py`` already
pins what ``stylize_tree_list`` does, and the bug was never in a helper -- it was
a call site that used half of one. Walking the built window is the only guard
that fails when someone builds the *next* label inline.

What it cannot see, and what covered it instead: whether wxMSW honoured any of
these calls. It accepts colours it then ignores (``docs/WXMSW_BEHAVIOUR.md``),
and this control has such a route -- the same foreground set on the
``wxDataViewMainWindow`` child changes nothing on screen while reading back
perfectly. The pixels were verified by capturing the running window through the
automation harness and counting them: near-black pixels in the client area went
6,240 -> 0.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from utils.constants import theme as T
from widgets.frames.match_history.frame import MatchHistoryFrame

#: Every colour the app's text scale offers. A ``wx.StaticText`` whose
#: foreground is outside this set has either escaped the styling layer entirely
#: (wx's default black) or grown a literal, which the palette guard in
#: ``tests/test_widget_audit.py`` bans separately.
TEXT_TOKENS: dict[tuple[int, int, int], str] = {
    T.TEXT_PRIMARY: "TEXT_PRIMARY",
    T.TEXT_SECONDARY: "TEXT_SECONDARY",
    T.TEXT_PLACEHOLDER: "TEXT_PLACEHOLDER",
    T.TEXT_DISABLED: "TEXT_DISABLED",
}


class _StubController:
    """The two calls ``MatchHistoryFrame`` makes on its controller."""

    def get_current_username(self) -> str | None:
        return None

    def parse_all_gamelogs(self, **_kwargs: Any) -> list[dict[str, Any]]:
        return []

    def infer_username_from_matches(self, _matches: list[dict[str, Any]]) -> str | None:
        return None


def _rgb(colour: wx.Colour) -> tuple[int, int, int]:
    return (colour.Red(), colour.Green(), colour.Blue())


def _walk(window: wx.Window) -> Iterator[wx.Window]:
    yield window
    for child in window.GetChildren():
        yield from _walk(child)


@pytest.fixture(name="history_frame")
def fixture_history_frame(wx_app: wx.App) -> Iterator[MatchHistoryFrame]:
    frame = MatchHistoryFrame(controller=_StubController())
    try:
        yield frame
    finally:
        frame.Destroy()
        pump_ui_events(wx_app)


def test_tree_rows_are_not_black(history_frame: MatchHistoryFrame) -> None:
    """The bug, at its call site: the tree had a background and no foreground."""
    tree = history_frame.tree
    assert _rgb(tree.GetBackgroundColour()) == T.SURFACE_ALT
    assert _rgb(tree.GetForegroundColour()) == T.TEXT_PRIMARY


def test_the_tree_wrapper_and_the_control_that_draws_it_agree(
    history_frame: MatchHistoryFrame,
) -> None:
    """``TreeListCtrl`` is a wrapper; the rows are drawn by the control inside it."""
    inner = history_frame.tree.GetDataView()
    assert _rgb(inner.GetBackgroundColour()) == T.SURFACE_ALT
    assert _rgb(inner.GetForegroundColour()) == T.TEXT_PRIMARY


def test_every_label_in_the_window_carries_a_text_token(
    history_frame: MatchHistoryFrame,
) -> None:
    """Catches the next caption someone builds inline, the way the two date ones were.

    Pinned on a count as well as on the offenders: a walk that stops finding
    labels would otherwise pass silently forever.
    """
    labels = [w for w in _walk(history_frame) if isinstance(w, wx.StaticText)]
    assert len(labels) >= 18, f"the walk found only {len(labels)} labels"

    offenders = [
        f"{label.GetLabel()!r} -> {_rgb(label.GetForegroundColour())}"
        for label in labels
        if _rgb(label.GetForegroundColour()) not in TEXT_TOKENS
    ]
    assert offenders == [], (
        "these labels never got a theme text colour, so wxMSW is painting them "
        f"in its default black on a dark surface: {offenders}"
    )
