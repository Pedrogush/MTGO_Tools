"""The deck builder's oracle ``Text`` filter, driven the way a user drives it.

Issue #1032: typing ``hexproof`` into the box returned every card in the
database. The box is a ``ManaSymbolRichCtrl`` whose ``GetValue()`` reports a
``_plain_text`` shadow of its buffer, and that shadow was only ever updated by
``SetValue``/``ChangeValue`` and by mana-symbol entry -- never by ordinary
typing, which the native rich-text control inserts on its own. The search read
``""`` and filtered nothing. The existing tests all set the box with
``ChangeValue``, the one path that worked, so they passed throughout.

So nothing here calls ``ChangeValue`` or the search service. Each test types
into the real box with key events delivered to the control's own handlers
(key-down, then the char event wx generates only when key-down is not eaten,
then key-up), picks ``=`` / ``≈`` on the real choice control, lets the panel's
own debounce timer start the search, and reads back the rows the results list
is showing.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import pytest
import wx

from repositories.card_repository import CardDataManager
from tests.ui.conftest import pump_ui_events

EXACT = 0  # "=" in the text-mode choice
WORDS = 1  # "≈"


def _card(name: str, text: str, back_text: str | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "name_lower": name.lower(),
        "mana_value": 1,
        "color_identity": [],
        "colors": [],
        "type_line": "Creature",
        "mana_cost": "{1}",
        "oracle_text": text,
        "back_oracle_text": back_text,
        "legalities": {"modern": "Legal"},
    }


CARDS = [
    _card(
        "Hexproof Bogle",
        "Hexproof (This creature can't be the target of spells or abilities "
        "your opponents control.)",
    ),
    _card("Flying Hexproof Angel", "Flying, hexproof"),
    _card(
        "Transforming Spirit",
        "At the beginning of your upkeep, transform this creature.",
        back_text="Hexproof",
    ),
    _card("Indestructible Blessing", "Target creature gains indestructible until end of turn."),
    _card("Mass Protection", "Permanents you control gain indestructible until end of turn."),
    _card("Split Guard", "Indestructible\nWhenever this creature attacks, it gains first strike."),
    _card(
        "Creature Target Bolt",
        "Deal 3 damage to any target. Draw a card if you control a creature.",
    ),
    _card("Fading Shield", "Until your next turn, target creature gains deathtouch."),
    _card("Scattered Turn", "Until the end of your next turn, you may play that card."),
    _card(
        "Deathtouch Lesson",
        "Creatures you control have deathtouch. Whenever a creature gains lifelink, "
        "you gain 1 life.",
    ),
    _card(
        "Humble",
        "Target creature loses all abilities and has base power and toughness 0/1 "
        "until end of turn.",
    ),
    _card("Blood Moon Variant", "Nonbasic lands lose all land types and abilities."),
    _card("Giant Spider", "Reach"),
    _card(
        "Monastery Swiftspear",
        "Haste\nProwess (Whenever you cast a noncreature spell, this creature gets +1/+1 "
        "until end of turn.)",
    ),
    _card("Tutor", "Search your library for a card, put that card into your hand, then shuffle."),
    _card("Library Search", "You may search your graveyard and library for a card."),
    _card("Vanilla Bear", ""),
    _card("Watchful Guard", "Vigilance"),
]

# query -> (names under "=", names under "≈").
# "=" is the phrase verbatim; "≈" is every word in any order, so "gains" also
# finds "gain" and "loses" finds "lose".
EXPECTED: dict[str, tuple[set[str], set[str]]] = {
    "hexproof": (
        {"Hexproof Bogle", "Flying Hexproof Angel", "Transforming Spirit"},
        {"Hexproof Bogle", "Flying Hexproof Angel", "Transforming Spirit"},
    ),
    "gains indestructible": (
        {"Indestructible Blessing"},
        {"Indestructible Blessing", "Mass Protection", "Split Guard"},
    ),
    "target creature": (
        {"Indestructible Blessing", "Fading Shield", "Humble"},
        {
            "Hexproof Bogle",
            "Indestructible Blessing",
            "Creature Target Bolt",
            "Fading Shield",
            "Humble",
        },
    ),
    "until end of turn": (
        {"Indestructible Blessing", "Mass Protection", "Humble", "Monastery Swiftspear"},
        {
            "Indestructible Blessing",
            "Mass Protection",
            "Scattered Turn",
            "Humble",
            "Monastery Swiftspear",
        },
    ),
    "until your next turn": (
        {"Fading Shield"},
        {"Fading Shield", "Scattered Turn"},
    ),
    "gains deathtouch": (
        {"Fading Shield"},
        {"Fading Shield", "Deathtouch Lesson"},
    ),
    "loses all abilities": (
        {"Humble"},
        {"Humble", "Blood Moon Variant"},
    ),
    "reach": ({"Giant Spider"}, {"Giant Spider"}),
    "prowess": ({"Monastery Swiftspear"}, {"Monastery Swiftspear"}),
    "search your library": (
        {"Tutor"},
        {"Tutor", "Library Search"},
    ),
}


# ---------------------------------------------------------------------------
# Driving the panel
# ---------------------------------------------------------------------------


def _run_event_loop(until: Callable[[], bool], timeout: float) -> None:
    """Dispatch real window messages until ``until()`` holds or time runs out.

    The search starts from the panel's ``wx.Timer`` and its result comes back
    through ``wx.CallAfter``. ``wx.App.Yield`` does nothing at all without an
    active event loop -- no WM_TIMER, no pending calls -- so ``pump_ui_events``
    would never see either; activating a ``GUIEventLoop`` for the wait makes
    them run exactly as they do under ``MainLoop``.
    """
    loop = wx.GUIEventLoop()
    activator = wx.EventLoopActivator(loop)
    try:
        deadline = time.monotonic() + timeout
        while not until() and time.monotonic() < deadline:
            wx.GetApp().Yield()
            time.sleep(0.01)
    finally:
        del activator


@pytest.fixture(name="builder")
def fixture_builder(wx_app, deck_selector_factory) -> Iterator[Any]:
    """An AppFrame showing the deck builder over the ``CARDS`` database."""
    frame = deck_selector_factory()
    manager = CardDataManager()
    manager._cards = CARDS
    manager._cards_by_name = {card["name_lower"]: card for card in CARDS}
    frame.card_data_dialogs_disabled = True
    frame.card_repo.set_card_manager(manager)
    frame.card_repo.set_card_data_loading(False)
    frame.card_repo.set_card_data_ready(True)
    frame.card_manager = manager
    frame.card_data_ready = True
    frame._show_left_panel("builder", force=True)
    # The results list would otherwise queue Scryfall image downloads for these
    # made-up cards once a live loop lets its prefetch timer fire.
    frame.builder_panel._on_prefetch_images = None
    pump_ui_events(wx_app)
    try:
        yield frame.builder_panel
    finally:
        # A one-shot wx.Timer still running when its owner is destroyed fires
        # into freed memory the next time a live loop dispatches WM_TIMER --
        # the frame's 600ms settings-save timer, started by the initial layout,
        # is usually still pending this soon. Stop them all first.
        for owner in (frame, frame.builder_panel):
            for value in list(vars(owner).values()):
                if isinstance(value, wx.Timer):
                    value.Stop()
        frame.Destroy()
        _run_event_loop(lambda: False, timeout=0.2)
        pump_ui_events(wx_app)


def _oracle_box(panel: Any) -> wx.Window:
    """The rich-text control that actually receives keystrokes."""
    return panel.inputs["text"]._inner


def _key_event(
    event_type: int, target: wx.Window, key_code: int, *, ctrl: bool = False, shift: bool = False
) -> wx.KeyEvent:
    evt = wx.KeyEvent(event_type)
    evt.SetEventObject(target)
    evt.SetId(target.GetId())
    evt.SetKeyCode(key_code)
    if 32 <= key_code < 127:
        evt.SetUnicodeKey(key_code)
    evt.SetControlDown(ctrl)
    evt.SetShiftDown(shift)
    return evt


def _press(
    target: wx.Window, key_code: int, char_code: int | None = None, **modifiers: bool
) -> None:
    """Deliver one keystroke: key-down, the char it produces, key-up.

    wx only generates the char event when the key-down handler skips, which
    ``ProcessEvent`` reports by returning False.
    """
    handler = target.GetEventHandler()
    handled = handler.ProcessEvent(_key_event(wx.wxEVT_KEY_DOWN, target, key_code, **modifiers))
    if not handled and char_code is not None:
        handler.ProcessEvent(_key_event(wx.wxEVT_CHAR, target, char_code, **modifiers))
    handler.ProcessEvent(_key_event(wx.wxEVT_KEY_UP, target, key_code, **modifiers))


def _type(target: wx.Window, text: str) -> None:
    target.SetFocus()
    for ch in text:
        _press(target, ord(ch.upper()), ord(ch))


def _choose_text_mode(panel: Any, selection: int) -> None:
    choice = panel.text_mode_choice
    choice.SetSelection(selection)
    evt = wx.CommandEvent(wx.wxEVT_CHOICE, choice.GetId())
    evt.SetEventObject(choice)
    evt.SetInt(selection)
    choice.GetEventHandler().ProcessEvent(evt)


def _shown_after_search(panel: Any, timeout: float = 10.0) -> list[str]:
    """Wait for the debounced search to repaint the list; return its rows."""
    updates: list[int] = []
    original = panel.update_results

    def spy(results: list[dict[str, Any]]) -> None:
        original(results)
        updates.append(len(results))

    panel.update_results = spy
    try:
        _run_event_loop(lambda: bool(updates), timeout)
    finally:
        del panel.update_results
    assert updates, "the oracle text box never started a search"
    results = panel.results_ctrl
    return [results.GetItemText(row) for row in range(results.GetItemCount())]


# ---------------------------------------------------------------------------
# Search semantics
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", [EXACT, WORDS], ids=["exact", "words"])
@pytest.mark.parametrize("query", list(EXPECTED))
def test_typed_oracle_query_shows_matching_cards(builder, query, mode):
    _choose_text_mode(builder, mode)
    _type(_oracle_box(builder), query)

    shown = _shown_after_search(builder)

    assert builder.inputs["text"].GetValue() == query
    assert sorted(shown) == sorted(EXPECTED[query][mode])


def test_switching_text_mode_reruns_search_on_typed_query(builder):
    _type(_oracle_box(builder), "gains indestructible")
    assert sorted(_shown_after_search(builder)) == sorted(EXPECTED["gains indestructible"][EXACT])

    _choose_text_mode(builder, WORDS)
    assert sorted(_shown_after_search(builder)) == sorted(EXPECTED["gains indestructible"][WORDS])


# ---------------------------------------------------------------------------
# Box behaviour: Enter, pasted line breaks, scrollbar arrows, Ctrl+Shift+M
# ---------------------------------------------------------------------------


def test_enter_does_not_insert_a_line_break(builder):
    box = _oracle_box(builder)
    _type(box, "hexproof")
    _press(box, wx.WXK_RETURN, wx.WXK_RETURN)
    _press(box, wx.WXK_NUMPAD_ENTER, wx.WXK_RETURN)

    shown = _shown_after_search(builder)

    assert builder.inputs["text"].GetValue() == "hexproof"
    assert box.GetBuffer().GetChildCount() == 1  # still a single paragraph
    assert sorted(shown) == sorted(EXPECTED["hexproof"][EXACT])


def test_pasted_line_break_is_folded_into_a_space(builder):
    box = _oracle_box(builder)
    box.SetFocus()
    box.WriteText("gains\nindestructible")  # inserted natively, as a paste is

    _run_event_loop(lambda: box.GetBuffer().GetChildCount() == 1, timeout=2.0)

    assert builder.inputs["text"].GetValue() == "gains indestructible"
    assert box.GetBuffer().GetChildCount() == 1


def _show_advanced_filters(panel: Any) -> None:
    if panel._adv_panel.IsShown():
        return
    button = panel._adv_toggle_btn
    evt = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    evt.SetEventObject(button)
    button.GetEventHandler().ProcessEvent(evt)
    _run_event_loop(lambda: False, timeout=0.2)


def _scrollbar_strip_is_clipped(box: wx.Window) -> bool:
    # A window's vertical scrollbar is the strip between its client area's
    # right edge and its own right edge; every pixel of it has to fall outside
    # the parent that clips it.
    clip = box.GetParent()
    strip_left = box.ClientToScreen(wx.Point(box.GetClientSize().width, 0)).x
    visible_right = clip.ClientToScreen(wx.Point(clip.GetClientSize().width, 0)).x
    return strip_left >= visible_right


def test_long_oracle_query_scrolls_without_showing_arrows(builder):
    _show_advanced_filters(builder)
    box = _oracle_box(builder)
    query = "target creature gains indestructible until end of turn " * 4
    _type(box, query)
    _run_event_loop(lambda: False, timeout=0.3)

    assert _scrollbar_strip_is_clipped(box)
    # The hidden scrollbar still scrolls the caret's wrapped line into view.
    assert box.GetFirstVisiblePosition() > 0
    assert builder.inputs["text"].GetValue() == query


def test_mana_cost_box_keeps_scrollbar_arrows_off_screen(builder):
    box = builder.inputs["mana"]._inner
    box.SetFocus()
    for _ in range(40):
        _press(box, ord("G"), ord("g"))
    _run_event_loop(lambda: False, timeout=0.3)

    assert builder.inputs["mana"].GetValue() == "{G}" * 40
    assert _scrollbar_strip_is_clipped(box)


def test_ctrl_shift_m_still_toggles_mana_symbol_typing(builder):
    box = _oracle_box(builder)
    _type(box, "add ")

    _press(box, ord("M"), None, ctrl=True, shift=True)
    assert box._mana_mode_active
    _press(box, ord("G"), ord("g"))
    _press(box, ord("G"), ord("g"))
    _press(box, ord("M"), None, ctrl=True, shift=True)
    assert not box._mana_mode_active
    _type(box, " x")

    assert builder.inputs["text"].GetValue() == "add {G}{G} x"
