"""The Documents folder the deck dialogs fall back to (#1034)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import utils.known_folders as known_folders


@pytest.mark.skipif(sys.platform != "win32", reason="the shell known-folder API is Windows-only")
def test_documents_resolves_through_the_shell_to_a_real_folder() -> None:
    shell = known_folders._known_folder_path(known_folders._FOLDERID_DOCUMENTS)
    assert shell is not None and shell.is_dir()
    assert known_folders.documents_dir() == shell


def test_falls_back_to_home_documents_when_the_shell_has_no_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "Documents").mkdir()
    monkeypatch.setattr(known_folders, "_known_folder_path", lambda _guid: None)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    assert known_folders.documents_dir() == tmp_path / "Documents"


def test_falls_back_to_home_when_there_is_no_documents_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(known_folders, "_known_folder_path", lambda _guid: tmp_path / "gone")
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))
    assert known_folders.documents_dir() == tmp_path
