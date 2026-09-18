"""The deck-action Save dropdown (#1044): Save Deck or Save Collection Diff.

``PopupMenu`` runs a nested modal loop that a headless test cannot dismiss, so
the menu is read through ``save_menu_entries`` -- the same list the click handler
renders -- and the callbacks it hands back are invoked directly.
"""

from __future__ import annotations

import pytest
import wx

from utils.constants import MENU_CARET
from widgets.buttons.deck_action_buttons import DeckActionButtons

LABELS = {"save_deck": "Save Deck", "save_diff": "Save Collection Diff"}


@pytest.fixture(name="buttons")
def fixture_buttons(wx_app):
    made: list[wx.Frame] = []

    def make(**kwargs) -> DeckActionButtons:
        frame = wx.Frame(None)
        made.append(frame)
        return DeckActionButtons(frame, labels=LABELS, **kwargs)

    yield make
    for frame in made:
        frame.Destroy()


def test_save_button_is_marked_as_a_dropdown(buttons) -> None:
    panel = buttons()

    # Save no longer fires on click, so it carries the same caret as the other
    # menu-opening buttons rather than looking like an immediate action.
    assert panel.save_button.GetLabel() == f"Save Deck {MENU_CARET}"


def test_save_menu_offers_the_deck_and_the_diff_in_that_order(buttons) -> None:
    calls: list[str] = []
    panel = buttons(
        on_save=lambda: calls.append("deck"),
        on_save_diff=lambda: calls.append("diff"),
    )

    entries = panel.save_menu_entries()

    assert [label for label, _cb in entries] == ["Save Deck", "Save Collection Diff"]
    for _label, callback in entries:
        callback()
    assert calls == ["deck", "diff"]


def test_save_menu_entries_without_callbacks_are_reported_as_none(buttons) -> None:
    """An unwired panel still builds its menu; the handler greys those items out."""
    panel = buttons()

    assert [callback for _label, callback in panel.save_menu_entries()] == [None, None]
