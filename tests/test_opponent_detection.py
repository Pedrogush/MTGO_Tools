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


@pytest.mark.parametrize(
    "titles, expected",
    [
        # Multiple 'vs.' segments: only the final segment is captured (split[-1]).
        (["Alice vs. Bob vs. Carol"], ["Carol"]),
        # Realistic full MTGO title with a trailing suffix on the opponent name;
        # the whole remainder after the last 'vs.' (stripped) is the opponent.
        (
            ["Magic: The Gathering Online — Match: Hero vs. Rival [Paused]"],
            ["Rival [Paused]"],
        ),
        # 'vs.' embedded inside a word (no boundary) still triggers a match;
        # this pins the chosen substring contract rather than a word-boundary one.
        (["elvs. Goblin"], ["Goblin"]),
        (["Champion advs. Underdog"], ["Underdog"]),
    ],
)
def test_find_opponent_names_split_and_matching_contract(
    monkeypatch: pytest.MonkeyPatch, titles: Iterable[str], expected: list[str]
) -> None:
    """Pin the split contract (last 'vs.' segment, suffix kept) and the substring-match contract."""
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


def test_find_opponent_names_empty_title_list(monkeypatch: pytest.MonkeyPatch) -> None:
    """No open windows yields no opponents."""
    monkeypatch.setattr(
        "utils.find_opponent_names.pygetwindow.getAllTitles",
        lambda: [],
    )
    assert find_opponent_names() == []


@pytest.mark.parametrize(
    "titles, expected",
    [
        (["Champion vs."], []),
        (["vs."], []),
        (["Champion vs. "], []),
        (["Champion vs. Rival", "Lobby vs."], ["Rival"]),
    ],
)
def test_find_opponent_names_skips_blank_opponents(
    monkeypatch: pytest.MonkeyPatch, titles: Iterable[str], expected: list[str]
) -> None:
    """A trailing 'vs.' yields an empty name that must not be emitted as an opponent."""
    monkeypatch.setattr(
        "utils.find_opponent_names.pygetwindow.getAllTitles",
        lambda: list(titles),
    )
    assert find_opponent_names() == expected
