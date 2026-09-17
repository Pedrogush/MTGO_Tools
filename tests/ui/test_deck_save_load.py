"""Save and Load Deck from the menu bar, the default deck folder, and the archetype (#1034).

Driven the way a user drives them: the ``Save`` and ``Load`` titles on the bar
are clicked (a real ``wx.EVT_BUTTON`` on the real title button), and the two
modal dialogs involved are replaced by recording fakes -- ``SaveDeckDialog`` for
the format and archetype, ``wx.FileDialog`` for Windows' Save As / Open. The
fakes record how they were constructed, which is where the folder a dialog opens
in is decided.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import wx

import controllers.app_controller.settings as controller_settings
from controllers.session_manager import DeckSelectorSessionManager
from widgets.preferences import apply_preference, find_preference

DECK_TEXT = "4 Mountain\n4 Island\n\nSideboard\n2 Dispel"
DETAILS_CLS = "widgets.frames.app_frame.handlers.deck_content.SaveDeckDialog"


class FakeFileDialog:
    """Stands in for ``wx.FileDialog``; answers with ``path`` or cancels."""

    instances: list[FakeFileDialog] = []
    path: str | None = None

    def __init__(self, parent, message="", defaultDir="", defaultFile="", wildcard="", style=0):
        self.kwargs = {
            "message": message,
            "defaultDir": defaultDir,
            "defaultFile": defaultFile,
            "style": style,
        }
        FakeFileDialog.instances.append(self)

    def __enter__(self) -> FakeFileDialog:
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def ShowModal(self) -> int:  # noqa: N802 - wx API
        return wx.ID_OK if FakeFileDialog.path else wx.ID_CANCEL

    def GetPath(self) -> str:  # noqa: N802 - wx API
        return FakeFileDialog.path or ""


class FakeDetailsDialog:
    """Stands in for ``SaveDeckDialog``; picks ``archetype`` in ``format``."""

    instances: list[FakeDetailsDialog] = []
    answer: tuple[str, str] = ("Modern", "")

    def __init__(self, parent, **kwargs: Any) -> None:
        self.kwargs = kwargs
        FakeDetailsDialog.instances.append(self)

    def ShowModal(self) -> int:  # noqa: N802 - wx API
        return wx.ID_OK

    def selected_format(self) -> str:
        return FakeDetailsDialog.answer[0]

    def selected_archetype(self) -> str:
        return FakeDetailsDialog.answer[1]

    def Destroy(self) -> None:  # noqa: N802 - wx API
        return None


def _scene(frame, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """One deck loaded, both dialogs faked, no default folder set."""
    FakeFileDialog.instances = []
    FakeFileDialog.path = None
    FakeDetailsDialog.instances = []
    FakeDetailsDialog.answer = ("Modern", "")
    documents = tmp_path / "Documents"
    documents.mkdir()
    # The Windows fallback, pinned so the test does not depend on the account.
    monkeypatch.setattr(controller_settings, "documents_dir", lambda: documents)
    frame.test_documents = documents  # type: ignore[attr-defined]
    # The option a previous test may have set; every test here starts unset.
    frame.controller.set_default_deck_save_path(None)
    frame.controller.deck_repo.set_current_deck_text(DECK_TEXT)
    frame.zone_cards = {
        "main": [{"name": "Mountain", "qty": 4}, {"name": "Island", "qty": 4}],
        "side": [{"name": "Dispel", "qty": 2}],
        "out": [],
    }
    with (
        patch("wx.FileDialog", FakeFileDialog),
        patch(DETAILS_CLS, FakeDetailsDialog),
        patch("wx.MessageBox"),
    ):
        yield frame


@pytest.fixture(name="frame")
def fixture_frame(shared_frame, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """The module's window (see ``shared_app_frame``), with the scene set up again.

    The saved-decks database is still per test -- ``ui_environment`` points
    ``DatabaseMixin._get_db_path`` at this test's tmp cache, and the path is
    resolved per call -- so a record one test saves is invisible to the next,
    which is what the content-matching tests need.
    """
    yield from _scene(shared_frame, tmp_path, monkeypatch)


@pytest.fixture(name="fresh_frame")
def fixture_fresh_frame(deck_selector_factory, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A newly built window, for the test that reads the settings file itself.

    A settings file belongs to the session manager that opened it, and the
    shared window's is the module's, not this test's ``ui_environment`` one.
    """
    frame = deck_selector_factory()
    try:
        yield from _scene(frame, tmp_path, monkeypatch)
    finally:
        frame.Destroy()


def _click_title(frame, title: str) -> None:
    """Click a title on the menu bar the way the mouse does: EVT_BUTTON on it."""
    button = frame.menu_bar._button_for(title)
    assert button is not None, f"no {title!r} title on the bar"
    event = wx.CommandEvent(wx.wxEVT_BUTTON, button.GetId())
    event.SetEventObject(button)
    button.ProcessEvent(event)


# ---------------------------------------------------------------------------- the bar


def test_the_bar_reads_file_tools_help_save_load(frame) -> None:
    assert frame.menu_bar.titles() == ["File", "Tools", "Help", "Save", "Load"]
    assert frame.menu_bar.is_action("Save") and frame.menu_bar.is_action("Load")
    assert not frame.menu_bar.is_action("File")


def test_save_and_load_titles_are_styled_exactly_like_the_menu_titles(frame) -> None:
    kind_attr = "_mtgo_button_kind"
    kinds = {
        title: getattr(frame.menu_bar._button_for(title), kind_attr)
        for title in frame.menu_bar.titles()
    }
    assert kinds["Save"] == kinds["Load"] == kinds["File"]
    assert kinds["File"][0] == "flat"


def test_file_menu_offers_load_and_save_deck(frame) -> None:
    labels = [entry.label for entry in frame.menu_bar.entries("File")]
    assert labels[:2] == ["Load Deck…", "Save Deck…"]


# ---------------------------------------------------------------------------- folder


def test_save_opens_save_as_in_the_default_deck_folder(frame, tmp_path: Path) -> None:
    folder = tmp_path / "my decks"
    folder.mkdir()
    frame.controller.set_default_deck_save_path(str(folder))

    _click_title(frame, "Save")

    assert len(FakeFileDialog.instances) == 1
    kwargs = FakeFileDialog.instances[0].kwargs
    assert kwargs["defaultDir"] == str(folder)
    assert kwargs["style"] & wx.FD_SAVE


def test_load_opens_in_the_same_default_deck_folder(frame, tmp_path: Path) -> None:
    folder = tmp_path / "my decks"
    folder.mkdir()
    frame.controller.set_default_deck_save_path(str(folder))

    _click_title(frame, "Load")

    assert [d.kwargs["defaultDir"] for d in FakeFileDialog.instances] == [str(folder)]
    assert FakeFileDialog.instances[0].kwargs["style"] & wx.FD_OPEN


def test_unset_folder_falls_back_to_documents(frame) -> None:
    assert frame.controller.get_default_deck_save_path() == ""

    _click_title(frame, "Save")
    _click_title(frame, "Load")

    documents = str(frame.test_documents)
    assert [d.kwargs["defaultDir"] for d in FakeFileDialog.instances] == [documents, documents]


def test_a_folder_that_no_longer_exists_falls_back_to_documents(frame, tmp_path: Path) -> None:
    frame.controller.set_default_deck_save_path(str(tmp_path / "deleted since"))

    _click_title(frame, "Load")

    assert FakeFileDialog.instances[0].kwargs["defaultDir"] == str(frame.test_documents)


# ---------------------------------------------------------------------------- archetype


def test_save_writes_the_file_and_records_format_and_archetype(frame, tmp_path: Path) -> None:
    target = tmp_path / "Izzet Murktide.txt"
    FakeFileDialog.path = str(target)
    FakeDetailsDialog.answer = ("Legacy", "Izzet Delver")

    _click_title(frame, "Save")

    assert target.read_text(encoding="utf-8") == DECK_TEXT
    record = frame.controller.deck_repo.find_saved_deck(file_path=target)
    assert record is not None
    assert (record["format"], record["archetype"], record["name"]) == (
        "Legacy",
        "Izzet Delver",
        "Izzet Murktide",
    )


def test_a_blank_archetype_saves_without_one(frame, tmp_path: Path) -> None:
    target = tmp_path / "Brew.txt"
    FakeFileDialog.path = str(target)
    FakeDetailsDialog.answer = ("Modern", "")

    _click_title(frame, "Save")

    record = frame.controller.deck_repo.find_saved_deck(file_path=target)
    assert record["archetype"] is None
    assert record["format"] == "Modern"


def test_cancelling_the_details_dialog_writes_nothing(frame, tmp_path: Path) -> None:
    FakeFileDialog.path = str(tmp_path / "never.txt")
    with patch.object(FakeDetailsDialog, "ShowModal", return_value=wx.ID_CANCEL):
        _click_title(frame, "Save")
    assert FakeFileDialog.instances == []
    assert not (tmp_path / "never.txt").exists()


def test_archetype_round_trips_through_save_and_load(frame, tmp_path: Path) -> None:
    target = tmp_path / "Round Trip.txt"
    FakeFileDialog.path = str(target)
    FakeDetailsDialog.answer = ("Pioneer", "Rakdos Midrange")
    _click_title(frame, "Save")

    # Start from a different deck so the load has something to replace.
    frame.controller.deck_repo.set_current_deck(None)
    rendered: list[tuple[str, str]] = []
    frame._on_deck_content_ready = lambda text, source="manual": rendered.append(  # type: ignore[assignment]
        (text, source)
    )
    _click_title(frame, "Load")

    assert rendered == [(DECK_TEXT, "file")]
    loaded = frame.controller.deck_repo.get_current_deck()
    assert loaded["archetype"] == "Rakdos Midrange"
    assert loaded["format"] == "Pioneer"
    assert "Rakdos Midrange" in frame.status_bar.GetStatusText()

    # ...and saving it again offers what it was saved with.
    FakeDetailsDialog.instances = []
    _click_title(frame, "Save")
    offered = FakeDetailsDialog.instances[0].kwargs
    assert offered["initial_format"] == "Pioneer"
    assert offered["initial_archetype"] == "Rakdos Midrange"


def test_a_moved_file_still_finds_its_archetype_by_content(frame, tmp_path: Path) -> None:
    original = tmp_path / "Original.txt"
    FakeFileDialog.path = str(original)
    FakeDetailsDialog.answer = ("Modern", "Boros Energy")
    _click_title(frame, "Save")

    moved = tmp_path / "elsewhere" / "Copied.txt"
    moved.parent.mkdir()
    moved.write_text(original.read_text(encoding="utf-8"), encoding="utf-8")
    FakeFileDialog.path = str(moved)
    frame._on_deck_content_ready = lambda text, source="manual": None  # type: ignore[assignment]
    _click_title(frame, "Load")

    assert frame.controller.deck_repo.get_current_deck()["archetype"] == "Boros Energy"


def test_a_research_deck_opens_the_dialog_on_its_list_format_and_archetype(frame) -> None:
    frame.controller.archetypes = [
        {"name": "Mono Red Aggro", "href": "mono-red-aggro"},
        {"name": "Azorius Control", "href": "azorius-control"},
    ]
    frame.controller.deck_repo.set_current_deck(
        {"name": "azorius-control", "number": "1", "player": "P", "source": "mtggoldfish"}
    )
    frame.controller.detect_deck_format = lambda _text: pytest.fail("known format, no guess")

    _click_title(frame, "Save")

    offered = FakeDetailsDialog.instances[0].kwargs
    assert offered["initial_format"] == frame.current_format
    assert offered["initial_archetype"] == "Azorius Control"


def test_an_unrecorded_deck_opens_the_dialog_on_the_detected_format(frame) -> None:
    frame.controller.deck_repo.set_current_deck(None)
    frame.controller.detect_deck_format = lambda _text: "Legacy"

    _click_title(frame, "Save")

    assert FakeDetailsDialog.instances[0].kwargs["initial_format"] == "Legacy"
    assert FakeDetailsDialog.instances[0].kwargs["initial_archetype"] == ""


def test_undetectable_format_falls_back_to_the_research_format(frame) -> None:
    frame.controller.deck_repo.set_current_deck(None)
    frame.controller.detect_deck_format = lambda _text: ""

    _click_title(frame, "Save")

    assert FakeDetailsDialog.instances[0].kwargs["initial_format"] == frame.current_format


# ---------------------------------------------------------------------------- the option


def test_the_default_folder_option_persists_and_clears(fresh_frame, tmp_path: Path) -> None:
    import utils.constants as constants

    frame = fresh_frame
    folder = tmp_path / "decks here"
    folder.mkdir()
    groups = frame.preference_groups()
    pref = find_preference(groups, "default_deck_save_path")
    assert pref is not None and pref.kind == "path" and pref.value == ""

    assert apply_preference(groups, "default_deck_save_path", str(folder))
    frame.controller.save_settings()
    settings_file = constants.DECK_SELECTOR_SETTINGS_FILE
    assert json.loads(settings_file.read_text(encoding="utf-8"))["default_deck_save_path"] == str(
        folder
    )
    # A fresh session reads it back.
    reread = DeckSelectorSessionManager(frame.controller.deck_repo, settings_file=settings_file)
    assert reread.get_default_deck_save_path() == str(folder)
    assert find_preference(frame.preference_groups(), "default_deck_save_path").value == str(folder)

    assert apply_preference(frame.preference_groups(), "default_deck_save_path", "clear")
    frame.controller.save_settings()
    assert "default_deck_save_path" not in json.loads(settings_file.read_text(encoding="utf-8"))


def test_the_option_refuses_a_folder_that_does_not_exist(frame, tmp_path: Path) -> None:
    groups = frame.preference_groups()
    assert not apply_preference(groups, "default_deck_save_path", str(tmp_path / "nope"))
    assert frame.controller.get_default_deck_save_path() == ""
