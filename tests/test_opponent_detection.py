from collections.abc import Iterable

import pytest

from utils.find_opponent_names import find_opponent_names


@pytest.mark.parametrize(
    "titles, expected",
    [
        (
            [
                "MTGO — Player Bootcamp vs. Champion",
                "Other window",
                "vs. SecondPlayer",
                "Not a match",
            ],
            ["Champion", "SecondPlayer"],
        ),
        (
            ["Waiting room vs. ThirdPlayer", "vs. FourthPlayer vs. FifthPlayer"],
            ["ThirdPlayer", "FifthPlayer"],
        ),
    ],
)
def test_find_opponent_names_detects_windows(
    monkeypatch: pytest.MonkeyPatch, titles: Iterable[str], expected: list[str]
) -> None:
    """Verify we capture opponent names from window titles containing vs."""
    monkeypatch.setattr(
        "utils.find_opponent_names.pygetwindow.getAllTitles",
        lambda: list(titles),
    )
    assert find_opponent_names() == expected


def test_find_opponent_names_ignores_non_match_titles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure titles without the vs. marker are skipped."""
    monkeypatch.setattr(
        "utils.find_opponent_names.pygetwindow.getAllTitles",
        lambda: ["MTGO Lobby", "Deck building", ""],
    )
    assert find_opponent_names() == []


@pytest.mark.parametrize(
    "titles",
    [
        ["Champion vs."],
        ["vs."],
        ["Champion vs. "],
        ["Champion vs. Rival", "Lobby vs."],
    ],
)
def test_find_opponent_names_skips_blank_opponents(
    monkeypatch: pytest.MonkeyPatch, titles: Iterable[str]
) -> None:
    """A trailing 'vs.' yields an empty name that must not be emitted as an opponent."""
    monkeypatch.setattr(
        "utils.find_opponent_names.pygetwindow.getAllTitles",
        lambda: list(titles),
    )
    assert "" not in find_opponent_names()
