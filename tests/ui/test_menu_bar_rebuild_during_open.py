"""#962: the menu bar survives being rebuilt from inside its own popup.

The crash this pins
-------------------
``File > Preferences... > Language`` reaches ``AppFrame._apply_language``, which
calls :meth:`AppMenuBar.set_menus` -- and its first act is
``sizer.Clear(delete_windows=True)``, destroying every title button. That happens
while :meth:`AppMenuBar.open_menu` is still suspended on the stack, so when
``PopupMenu`` finally returned, ``open_menu`` un-highlighted the button it had
opened with and that button was a dead C++ object::

    RuntimeError: wrapped C/C++ object of type Button has been deleted
      widgets/menu_bar/panel.py:104  in open_menu  -> self._highlight(button, False)
      widgets/stylize.py:820         in stylize_button -> button.IsThisEnabled()

Two orderings make it reachable, and **both were measured with real Win32 input
rather than assumed** (recorded in ``docs/WXMSW_BEHAVIOUR.md``, "nested modal
loops"): a popup menu item's handler runs *before* ``PopupMenu`` returns, and a
``ShowModal`` opened from that handler nests inside it -- as does every
``wx.CallAfter`` either one queues.

Why the popup is stubbed here
-----------------------------
Nothing below fakes that ordering; it removes the need for a real menu and real
keystrokes. ``_popup_runs`` calls its payload at exactly the point wxMSW
dispatches the chosen item, which is what makes the sequence deterministic in a
test. The end-to-end path was driven by hand against the running app, where it
crashes without the fix and does not with it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

import pytest
import wx

from tests.ui.conftest import pump_ui_events
from widgets.menu_bar import AppMenuBar, MenuEntry, MenuSpec

#: Set on a button by ``stylize_button``; see ``widgets.stylize._BUTTON_KIND_ATTR``.
BUTTON_KIND_ATTR = "_mtgo_button_kind"

#: The bar's titles either side of a language switch. The point of the pt-BR row
#: is that *no* title survives translation, so a post-popup lookup by title
#: correctly finds nothing at all.
EN = ("File", "Tools", "Help")
PT = ("Arquivo", "Ferramentas", "Ajuda")


def _specs(titles: Sequence[str]) -> list[MenuSpec]:
    return [MenuSpec(title, lambda t=title: [MenuEntry(label=f"{t} item")]) for title in titles]


def _kinds(bar: AppMenuBar) -> dict[str, str]:
    """``{label: stylize kind}`` for every live title button on the bar."""
    return {
        child.GetLabel(): getattr(child, BUTTON_KIND_ATTR)[0]
        for child in bar.GetChildren()
        if isinstance(child, wx.Button)
    }


@pytest.fixture(name="bar")
def fixture_bar(wx_app: wx.App):
    """A real menu bar on a real frame, torn down after the test.

    A bare frame rather than the whole app frame: this is a lifetime test, and
    ``tests/ui`` runs close enough to the Windows USER-handle ceiling that a
    ~1200-handle ``AppFrame`` per case is not worth spending here.
    """
    frame = wx.Frame(None)
    sizer = wx.BoxSizer(wx.VERTICAL)
    frame.SetSizer(sizer)
    bar = AppMenuBar(frame, _specs(EN))
    sizer.Add(bar, 0, wx.EXPAND)
    frame.Layout()
    yield bar
    frame.Destroy()
    pump_ui_events(wx_app)


def _popup_runs(monkeypatch: pytest.MonkeyPatch, payload: Callable[[], None]) -> None:
    """Make ``PopupMenu`` run ``payload`` and return, the way a real pick does.

    The popup is anchored on the *title button*, so the patch goes on
    ``wx.Window`` rather than on the bar -- and the button may well not survive
    the payload, which is the whole point.
    """

    def fake(self, menu, pos=wx.DefaultPosition):  # noqa: ANN001, ARG001
        payload()
        return True

    monkeypatch.setattr(wx.Window, "PopupMenu", fake)


def test_open_menu_survives_the_bar_being_rebuilt_from_inside_the_popup(
    bar: AppMenuBar, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Exactly what _apply_language does, from exactly where the language control
    # does it: while open_menu is blocked below PopupMenu.
    _popup_runs(monkeypatch, lambda: bar.set_menus(_specs(PT)))

    assert bar.open_menu("File") is True  # raised RuntimeError before the fix

    assert bar.titles() == list(PT)


def test_a_rebuild_leaves_no_title_stuck_in_the_open_highlight(
    bar: AppMenuBar, monkeypatch: pytest.MonkeyPatch
) -> None:
    _popup_runs(monkeypatch, lambda: bar.set_menus(_specs(PT)))

    bar.open_menu("File")

    # The highlight belongs to a button, not to a title: the button that carried
    # it is gone, and _build stylizes the replacements "flat" already. There is
    # nothing to hand the highlight back to, and nothing wearing it.
    assert _kinds(bar) == dict.fromkeys(PT, "flat")


def test_open_menu_still_takes_the_highlight_off_when_nothing_is_rebuilt(
    bar: AppMenuBar, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The ordinary case, pinned so that re-resolving the button after the popup
    # cannot quietly stop finding it and leave every opened title lit.
    during: dict[str, str] = {}
    _popup_runs(monkeypatch, lambda: during.update(_kinds(bar)))

    assert bar.open_menu("File") is True

    assert during["File"] == "ghost"
    assert _kinds(bar) == dict.fromkeys(EN, "flat")
