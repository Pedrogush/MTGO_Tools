"""Phase 8's sweep, as a guard: no live sizer may want more than it was given.

Why this is a *runtime* test and why it walks sizers rather than controls
------------------------------------------------------------------------
``wxSizer`` overflow is silent, and it is silent in two different shapes:

* **horizontal** -- when a row's minimum widths exceed the client, wxSizer
  neither shrinks the items proportionally nor clips the row. The first *n-1*
  items render at exactly their minimums and the **last** absorbs the whole
  deficit. Phase 7 measured the deck-workspace header's printing button painted
  14px wide against a 59px minimum, with every control to its left pixel-perfect;
* **vertical** -- when the fixed items alone exceed the client, the proportional
  item's share goes negative, is clamped to 0 (so the one thing meant to absorb
  the slack disappears), and the items *after* it are still laid out below the
  bottom edge. Phase 8 measured the deck builder's results list at exactly 0px
  with "Showing N cards." off-screen.

Neither is visible from any single control, which is why four phases of
screenshot review walked past both. It is visible from the sizer: ``CalcMin()``
against ``GetSize()``, everywhere, in one pass.

The two things this pins that a source-reading test cannot
---------------------------------------------------------
1. **Locale.** Phase 7's overflow only existed in pt-BR; en-US at the same width
   had 55px to spare. A row verified in one locale is not verified, so this
   parametrizes over both.
2. **The floor.** Every one of these defects appears only at the window's own
   enforced minimum, which is the size no screenshot pass had ever used -- the
   original review was conducted maximised at 2560x1040.
"""

from __future__ import annotations

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from utils.i18n import SUPPORTED_LOCALES

#: Sizers whose overflow is a scroll offset rather than a defect: a scrolled
#: window's content is *expected* to exceed its viewport along the scroll axis,
#: and reporting that is how it asks for a scrollbar.
_SCROLLED = (wx.ScrolledWindow, wx.grid.Grid)


def _inside_scroller(window: wx.Window) -> bool:
    node: wx.Window | None = window
    while node is not None:
        if isinstance(node, _SCROLLED):
            return True
        node = node.GetParent()
    return False


def _describe(window: wx.Window) -> str:
    parts = []
    node: wx.Window | None = window
    for _ in range(6):
        if node is None:
            break
        parts.append(type(node).__name__)
        node = node.GetParent()
    return "/".join(reversed(parts))


def _sizer_offenders(window: wx.Window, sizer: wx.Sizer, depth: int = 0) -> list[str]:
    """Every sizer at or under *sizer* that wants more than it holds."""
    found: list[str] = []
    if sizer is None or depth > 16:
        return found
    have = sizer.GetSize()
    want = sizer.CalcMin()
    short_w = want.width - have.width
    short_h = want.height - have.height
    # A sizer that has never been laid out reports a degenerate size; only a
    # sizer with a real box can be short of it.
    if have.width > 1 and have.height > 1:
        axes = []
        if short_w > 0:
            axes.append(f"{short_w}px wide")
        if short_h > 0 and not _inside_scroller(window):
            axes.append(f"{short_h}px tall")
        if axes:
            items = ", ".join(
                f"{type(i.GetWindow()).__name__ if i.GetWindow() else '<sizer>'}"
                f" {i.GetSize().width}x{i.GetSize().height}"
                f" (min {i.CalcMin().width}x{i.CalcMin().height})"
                for i in sizer.GetChildren()
            )
            found.append(
                f"{_describe(window)} is short {' and '.join(axes)} "
                f"(has {have.width}x{have.height}, wants {want.width}x{want.height}): {items}"
            )
    for item in sizer.GetChildren():
        child = item.GetSizer()
        if child is not None:
            found.extend(_sizer_offenders(window, child, depth + 1))
    return found


def _walk_windows(window: wx.Window, depth: int = 0) -> list[str]:
    # The frame itself is never Show()n in a test, and a hidden window still
    # lays its children out -- so the root is walked unconditionally and only
    # its descendants are filtered on visibility. Gating on IsShown() at depth 0
    # made a first draft of this file pass while visiting nothing at all.
    if depth > 30 or (depth and not window.IsShown()):
        return []
    found = _sizer_offenders(window, window.GetSizer())
    for child in window.GetChildren():
        found.extend(_walk_windows(child, depth + 1))
    return found


def _count_sizers(window: wx.Window, depth: int = 0) -> int:
    if depth > 30 or (depth and not window.IsShown()):
        return 0
    total = 0

    def count(sizer: wx.Sizer, d: int = 0) -> int:
        if sizer is None or d > 16:
            return 0
        n = 1
        for item in sizer.GetChildren():
            child = item.GetSizer()
            if child is not None:
                n += count(child, d + 1)
        return n

    total += count(window.GetSizer())
    for child in window.GetChildren():
        total += _count_sizers(child, depth + 1)
    return total


@pytest.mark.parametrize("locale", sorted(SUPPORTED_LOCALES))
def test_no_live_sizer_is_short_of_what_it_holds(deck_selector_factory, wx_app, locale) -> None:
    """At the enforced minimum, in both locales, every sizer fits its contents.

    The locale is written to settings **before** the frame is built rather than
    switched afterwards: ``_apply_language`` re-translates the menu bar and
    nothing else -- every panel took its strings at construction, which is why
    the preferences dialog's own help text says a restart is needed for the
    rest. Switching a live frame would have parametrized over nothing.
    """
    import json

    from utils.constants import DECK_SELECTOR_SETTINGS_FILE

    DECK_SELECTOR_SETTINGS_FILE.write_text(json.dumps({"language": locale}), encoding="utf-8")
    frame = deck_selector_factory()
    try:
        assert frame.locale == locale, "the frame did not pick the locale up from settings"
        pump_ui_events(wx_app)
        frame._apply_min_size()
        frame.SetSize(frame.GetMinSize())
        frame.Layout()
        pump_ui_events(wx_app)

        # Pinned so the sweep cannot pass by visiting nothing -- the failure
        # mode a first draft of this file actually had.
        visited = _count_sizers(frame)
        assert visited > 40, f"the sweep only reached {visited} sizers"

        offenders = _walk_windows(frame)
        assert offenders == [], "\n".join(["sizers short of their own contents:", *offenders])
    finally:
        frame.Destroy()
