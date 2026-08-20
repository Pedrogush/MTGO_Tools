"""Every notebook tab must be *drawn*, at the window's enforced minimum, in both locales.

The defect this encodes (phase 9, issue #962)
---------------------------------------------
At the main window's own enforced minimum width the deck workspace's
``FlatNotebook`` draws only **three** of its four tabs. ``Deck Stats`` -- the tab
phase 5 existed to make reachable, and which acceptance criterion "The Stats tab
is reachable" is about -- is simply not painted, and because the notebook is
built with ``FNB_NO_NAV_BUTTONS`` there is no arrow, no chevron and no overflow
menu either. There is no indication that a fourth tab exists. Measured on the
running app at **1267x882 (en-US)** and **1332x882 (pt-BR)**, both of which the
app enforces as its minimum and therefore claims to support.

Measured thresholds -- strip width needed for all four tabs:

===========  =========================  =====================
locale       sum of ``CalcTabWidth``    strip width needed
===========  =========================  =====================
en-US        358 px                     **384 px**
pt-BR        419 px                     **434 px**
===========  =========================  =====================

Why no earlier phase caught it
------------------------------
Phase 8's ``test_live_layout_overflow`` compares every sizer's ``CalcMin()``
against its ``GetSize()``. FlatNotebook does not overflow its sizer when its tabs
do not fit -- it *drops* tabs and reports a size that fits. Content disappearing
is invisible to a geometry check, which is why this needs its own guard.

Why this is ``xfail(strict=True)`` rather than a fix
---------------------------------------------------
Every route out is a decision the redesign's author should take, not one to make
silently in the closing phase:

* **shorten the labels** (``Deck Tables`` -> ``Tables`` and so on -- the word
  "Deck" appears three times inside a panel already called the deck workspace).
  Fixes it in both locales with no new chrome, but renames four user-facing tabs
  and the strings ``switch-tab`` is driven by;
* **drop ``FNB_NO_NAV_BUTTONS``** so the strip grows arrows. Those arrows are
  drawn by ``FNBRendererDefault`` in system colours, i.e. new light chrome on a
  dark strip -- which is acceptance criterion 1;
* **raise the enforced minimum width**, undoing the thing phase 8 achieved.

Strict xfail means the day one of those lands, this test XPASSes and *fails*,
which is the prompt to delete the marker rather than the file.

FlatNotebook API note, measured here
------------------------------------
``PageContainer.IsTabVisible(i)`` and ``GetLastVisibleTab()`` are **wrong for the
last tab**: with all four tabs drawn on screen at a 884px strip they still report
``IsTabVisible(3) is False`` and ``GetLastVisibleTab() == 2``.
``GetNumOfVisibleTabs()`` is the reliable one. All three are computed during
``DrawTabs``, so they read as "nothing is visible" until the strip has actually
painted -- hence the ``Show()`` + ``Update()`` below, which no other test in
``tests/ui`` needs.
"""

from __future__ import annotations

import json

import pytest
import wx
import wx.lib.agw.flatnotebook as fnb

from tests.ui.conftest import pump_ui_events
from utils.constants import DECK_SELECTOR_SETTINGS_FILE
from utils.i18n import SUPPORTED_LOCALES


def _notebooks(window: wx.Window, depth: int = 0) -> list[fnb.FlatNotebook]:
    if depth > 30:
        return []
    found: list[fnb.FlatNotebook] = []
    if isinstance(window, fnb.FlatNotebook):
        found.append(window)
    for child in window.GetChildren():
        found.extend(_notebooks(child, depth + 1))
    return found


def _dropped(notebook: fnb.FlatNotebook) -> int:
    """How many of this notebook's pages have no tab on screen."""
    return notebook.GetPageCount() - notebook._pages.GetNumOfVisibleTabs()


@pytest.mark.xfail(
    strict=True,
    reason=(
        "The deck workspace drops its 'Deck Stats' tab at the enforced minimum "
        "width in both locales, with FNB_NO_NAV_BUTTONS leaving no way to reach "
        "it. Needs a decision -- see this module's docstring."
    ),
)
@pytest.mark.parametrize("locale", sorted(SUPPORTED_LOCALES))
def test_every_notebook_page_has_a_visible_tab_at_the_minimum(
    deck_selector_factory, wx_app, locale
) -> None:
    DECK_SELECTOR_SETTINGS_FILE.write_text(json.dumps({"language": locale}), encoding="utf-8")
    frame = deck_selector_factory()
    try:
        assert frame.locale == locale, "the frame did not pick the locale up from settings"
        pump_ui_events(wx_app)
        frame._apply_min_size()
        frame.SetSize(frame.GetMinSize())
        frame.Layout()
        # The visibility counters are a side effect of DrawTabs, so the strip has
        # to have painted at least once before they mean anything.
        frame.Show()
        frame.Update()
        pump_ui_events(wx_app)

        books = _notebooks(frame)
        assert books, "no FlatNotebook found; this guard would pass by visiting nothing"

        offenders = [
            f"{type(b.GetParent()).__name__}/FlatNotebook: "
            f"{_dropped(b)} of {b.GetPageCount()} tabs not drawn "
            f"({[b.GetPageText(i) for i in range(b.GetPageCount())]}) "
            f"in a {b._pages.GetSize().width}px strip"
            for b in books
            if b.GetPageCount() and _dropped(b) > 0
        ]
        assert offenders == [], f"{locale} at {frame.GetSize()}: " + "; ".join(offenders)
    finally:
        frame.Hide()
