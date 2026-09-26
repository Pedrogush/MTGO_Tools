"""Save Collection Diff from the frame (#1044): the guards and the round trip.

Driven through ``AppFrame.on_save_diff_clicked`` with Windows' Save As replaced
by a recording mock, the way ``test_deck_selector``'s save tests drive Save Deck.
The diff arithmetic itself is covered by ``tests/test_collection_diff.py``; what
is under test here is the wiring -- which guard fires when, and what reaches the
file the user picked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
import wx

DECK_ZONES = {
    "main": [{"name": "Mountain", "qty": 4}, {"name": "Lightning Bolt", "qty": 4}],
    "side": [],
    "out": [],
}


@pytest.fixture(name="frame")
def fixture_frame(wx_app, deck_selector_factory):
    frame = deck_selector_factory()
    frame.zone_cards = dict(DECK_ZONES)
    yield frame
    frame.Destroy()


def _save_to(frame, path: Path) -> list[tuple[Path, str]]:
    """Run the handler with Save As answering *path*; return what was written."""
    written: list[tuple[Path, str]] = []

    def fake_write(file_path, content):
        written.append((Path(file_path), content))
        return Path(file_path)

    frame.controller.deck_repo.write_deck_file = fake_write  # type: ignore[assignment]
    with patch("wx.FileDialog") as dialog_cls, patch("wx.MessageBox"):
        dialog = dialog_cls.return_value.__enter__.return_value
        dialog.ShowModal.return_value = wx.ID_OK
        dialog.GetPath.return_value = str(path)
        frame.on_save_diff_clicked(None)
    return written


def test_save_diff_writes_only_the_missing_copies(frame, tmp_path: Path) -> None:
    frame.controller.collection_service.set_inventory({"mountain": 4, "lightning bolt": 1})

    written = _save_to(frame, tmp_path / "missing.txt")

    assert len(written) == 1
    # Mountain is covered and drops out; only the 3 Bolts still needed are saved.
    assert written[0][1] == "3 Lightning Bolt"


def test_save_diff_without_a_collection_warns_instead_of_saving_the_deck(frame) -> None:
    frame.controller.collection_service.clear_inventory()

    with patch("wx.FileDialog") as dialog_cls, patch("wx.MessageBox") as message_box:
        frame.on_save_diff_clicked(None)

    # No inventory means every card reads as missing; saving that would hand the
    # user their own decklist back under a "missing cards" name.
    assert message_box.called
    assert not dialog_cls.called


def test_save_diff_of_a_fully_owned_deck_says_so_instead_of_saving_nothing(frame) -> None:
    frame.controller.collection_service.set_inventory({"mountain": 4, "lightning bolt": 4})

    with patch("wx.FileDialog") as dialog_cls, patch("wx.MessageBox") as message_box:
        frame.on_save_diff_clicked(None)

    assert message_box.called
    assert not dialog_cls.called


def test_save_diff_with_no_deck_loaded_warns(frame) -> None:
    frame.zone_cards = {"main": [], "side": [], "out": []}
    frame.controller.collection_service.set_inventory({"mountain": 4})

    with patch("wx.FileDialog") as dialog_cls, patch("wx.MessageBox") as message_box:
        frame.on_save_diff_clicked(None)

    assert message_box.called
    assert not dialog_cls.called


def test_save_diff_forces_a_txt_extension(frame, tmp_path: Path) -> None:
    frame.controller.collection_service.set_inventory({"mountain": 4})

    written = _save_to(frame, tmp_path / "missing")

    assert written[0][0].suffix == ".txt"
