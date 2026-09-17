"""The Save Deck details dialog (issue #1034): format pre-selected, archetype from the list.

The archetype list is handed in as a loader so the dialog never reaches for the
metagame repository itself; these tests give it a synchronous one, and a
deferred one where the order of deliveries is the thing under test.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
import wx

from utils.i18n import translate
from widgets.dialogs.save_deck_dialog import SaveDeckDialog

FORMATS = ["Modern", "Pioneer", "Legacy"]
LISTS = {
    "Modern": ["Murktide", "Boros Energy", "amulet titan"],
    "Pioneer": ["Rakdos Midrange"],
    "Legacy": [],
}


def _t(key: str, **kwargs: object) -> str:
    return translate("en-US", key, **kwargs)


def _sync_loader(requests: list[str]) -> Callable[[str, Callable[[list[str]], None]], None]:
    def load(fmt: str, deliver: Callable[[list[str]], None]) -> None:
        requests.append(fmt)
        deliver(list(LISTS.get(fmt, [])))

    return load


def _select_format(dlg: SaveDeckDialog, name: str) -> None:
    choice = dlg.format_choice
    choice.SetStringSelection(name)
    event = wx.CommandEvent(wx.wxEVT_CHOICE, choice.GetId())
    event.SetEventObject(choice)
    event.SetInt(choice.GetSelection())
    choice.ProcessEvent(event)


@pytest.fixture(name="make_dialog")
def fixture_make_dialog(wx_app):
    made: list[SaveDeckDialog] = []

    def make(**kwargs) -> SaveDeckDialog:
        kwargs.setdefault("formats", FORMATS)
        kwargs.setdefault("initial_format", "Modern")
        kwargs.setdefault("load_archetypes", _sync_loader([]))
        dlg = SaveDeckDialog(None, t=_t, **kwargs)
        made.append(dlg)
        return dlg

    yield make
    for dlg in made:
        dlg.Destroy()


def test_opens_on_the_detected_format_with_that_formats_archetypes(make_dialog) -> None:
    requests: list[str] = []
    dlg = make_dialog(initial_format="Modern", load_archetypes=_sync_loader(requests))

    assert dlg.selected_format() == "Modern"
    assert requests == ["Modern"]
    # Sorted case-insensitively so a long metagame list is scannable by letter.
    assert dlg.archetype_names() == ["amulet titan", "Boros Energy", "Murktide"]
    assert dlg.archetype_choice.GetString(0) == _t("deck_save.archetype_none")


def test_archetype_defaults_to_none_and_blank_is_allowed(make_dialog) -> None:
    dlg = make_dialog()
    assert dlg.archetype_choice.GetSelection() == 0
    assert dlg.selected_archetype() == ""


def test_picking_an_archetype_from_the_list_is_what_selected_archetype_returns(
    make_dialog,
) -> None:
    dlg = make_dialog()
    dlg.archetype_choice.SetSelection(dlg.archetype_names().index("Murktide") + 1)
    assert dlg.selected_archetype() == "Murktide"


def test_initial_archetype_is_preselected(make_dialog) -> None:
    dlg = make_dialog(initial_archetype="Boros Energy")
    assert dlg.selected_archetype() == "Boros Energy"


def test_a_recorded_archetype_missing_from_the_list_survives_a_resave(make_dialog) -> None:
    dlg = make_dialog(initial_archetype="Hammer Time")
    assert "Hammer Time" in dlg.archetype_names()
    assert dlg.selected_archetype() == "Hammer Time"


def test_changing_the_format_reloads_the_archetype_list(make_dialog) -> None:
    requests: list[str] = []
    dlg = make_dialog(initial_archetype="Murktide", load_archetypes=_sync_loader(requests))

    _select_format(dlg, "Pioneer")

    assert requests == ["Modern", "Pioneer"]
    assert dlg.selected_format() == "Pioneer"
    assert dlg.archetype_names() == ["Rakdos Midrange"]
    # Murktide is not a Pioneer archetype, so the selection falls back to none.
    assert dlg.selected_archetype() == ""


def test_a_late_delivery_for_an_abandoned_format_is_ignored(make_dialog) -> None:
    pending: dict[str, Callable[[list[str]], None]] = {}

    def deferred(fmt: str, deliver: Callable[[list[str]], None]) -> None:
        pending[fmt] = deliver

    dlg = make_dialog(load_archetypes=deferred)
    assert not dlg.archetype_choice.IsEnabled()  # still loading

    _select_format(dlg, "Pioneer")
    pending["Pioneer"](LISTS["Pioneer"])
    pending["Modern"](LISTS["Modern"])  # arrives last, for a format no longer shown

    assert dlg.selected_format() == "Pioneer"
    assert dlg.archetype_names() == ["Rakdos Midrange"]
    assert dlg.archetype_choice.IsEnabled()


def test_an_unknown_initial_format_is_still_offered(make_dialog) -> None:
    dlg = make_dialog(initial_format="Premodern")
    assert dlg.selected_format() == "Premodern"
