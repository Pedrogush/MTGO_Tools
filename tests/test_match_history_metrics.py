"""Tests for the wx-free compute kernels of the match history viewer.

These cover the pure functions extracted from
``widgets/frames/match_history/handlers.py`` into ``properties.py``:
``resolve_match_perspective``, ``compute_history_metrics`` and
``compute_opponent_stats``. They also cover the wx-free helper methods on
``MatchHistoryPropertiesMixin`` (``_iter_matches``, ``_parse_date`` and
``_within_range``), which read only ``current_username`` and their arguments,
so they can be exercised on a bare mixin instance. ``wx`` is not importable in
the WSL dev environment and the package ``__init__`` pulls in the wx-dependent
frame, so ``properties.py`` is loaded directly by file path.
"""

from __future__ import annotations

import importlib.util
import types
from datetime import date, datetime
from pathlib import Path


def _load_properties_module() -> types.ModuleType:
    """Import the match history ``properties.py`` directly by file path."""
    path = (
        Path(__file__).resolve().parent.parent
        / "widgets"
        / "frames"
        / "match_history"
        / "properties.py"
    )
    spec = importlib.util.spec_from_file_location("_mh_properties_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_props = _load_properties_module()
resolve_match_perspective = _props.resolve_match_perspective
compute_history_metrics = _props.compute_history_metrics
compute_opponent_stats = _props.compute_opponent_stats
MatchHistoryPropertiesMixin = _props.MatchHistoryPropertiesMixin


def _make_mixin(current_username: str | None) -> object:
    """Bind the wx-free mixin methods to a stub carrying ``current_username``.

    The mixin has no ``__init__`` (state lives on the wx frame), and the
    methods exercised here (``_iter_matches``, ``_parse_date``,
    ``_within_range``) only read ``current_username``, so a bare subclass with
    that attribute set is a faithful, wx-free harness.
    """

    obj = MatchHistoryPropertiesMixin.__new__(MatchHistoryPropertiesMixin)
    obj.current_username = current_username
    return obj


# ----------------------------------------------------------------- resolve_match_perspective
def test_resolve_perspective_player1_is_us() -> None:
    match = {
        "players": ["me", "them"],
        "winner": "me",
        "match_score": "2-1",
        "player1_archetype": "Burn",
        "player2_archetype": "Control",
        "player1_mulligans": [1, 0],
        "player2_mulligans": [0],
    }
    out = resolve_match_perspective(match, "me")
    assert out["our_name"] == "me"
    assert out["opp_name"] == "them"
    assert out["our_archetype"] == "Burn"
    assert out["opp_archetype"] == "Control"
    assert out["our_mulligans"] == [1, 0]
    assert out["our_score"] == 2
    assert out["opp_score"] == 1
    assert out["we_won"] is True


def test_resolve_perspective_player2_is_us() -> None:
    match = {
        "players": ["them", "me"],
        "winner": "them",
        "match_score": "2-0",
        "player1_archetype": "Control",
        "player2_archetype": "Burn",
        "player1_mulligans": [0],
        "player2_mulligans": [1, 1],
    }
    out = resolve_match_perspective(match, "ME")  # case-insensitive
    assert out["our_name"] == "me"
    assert out["opp_name"] == "them"
    assert out["our_archetype"] == "Burn"
    assert out["opp_archetype"] == "Control"
    assert out["our_mulligans"] == [1, 1]
    assert out["our_score"] == 0
    assert out["opp_score"] == 2
    assert out["we_won"] is False


def test_resolve_perspective_no_username_defaults_to_player1() -> None:
    match = {"players": ["a", "b"], "winner": "b", "match_score": "1-2"}
    out = resolve_match_perspective(match, None)
    assert out["our_name"] == "a"
    assert out["opp_name"] == "b"
    assert out["our_score"] == 1
    assert out["opp_score"] == 2
    assert out["we_won"] is False


def test_resolve_perspective_bad_score_falls_back_to_zero() -> None:
    out = resolve_match_perspective({"players": ["a", "b"], "match_score": "??"}, None)
    assert out["our_score"] == 0
    assert out["opp_score"] == 0


def test_resolve_perspective_unknown_username_defaults_to_player1() -> None:
    # A username present but matching neither player must fall back to player1
    # being "us", as documented. (Regression: player2 was wrongly treated as us.)
    match = {
        "players": ["a", "b"],
        "winner": "a",
        "match_score": "2-1",
        "player1_archetype": "Burn",
        "player2_archetype": "Control",
    }
    out = resolve_match_perspective(match, "zzz")
    assert out["our_name"] == "a"
    assert out["opp_name"] == "b"
    assert out["our_archetype"] == "Burn"
    assert out["opp_archetype"] == "Control"
    assert out["our_score"] == 2
    assert out["opp_score"] == 1
    assert out["we_won"] is True


def test_resolve_perspective_missing_players_defaults_to_unknown() -> None:
    out = resolve_match_perspective({"players": []}, None)
    assert out["our_name"] == "Unknown"
    assert out["opp_name"] == "Unknown"


def test_resolve_perspective_missing_winner_we_won_false() -> None:
    out = resolve_match_perspective({"players": ["a", "b"], "match_score": "2-0"}, None)
    assert out["we_won"] is False


# -------------------------------------------------------------------- compute_history_metrics
def _metric(match_win: bool, won: int, total: int, mulls: int) -> dict[str, object]:
    return {
        "match_win": match_win,
        "games_won": won,
        "games_total": total,
        "total_mulligans": mulls,
    }


def test_compute_history_metrics_empty_returns_none() -> None:
    assert compute_history_metrics([], []) is None


def test_compute_history_metrics_aggregates() -> None:
    matches = [
        _metric(True, 2, 3, 1),
        _metric(False, 1, 2, 2),
    ]
    out = compute_history_metrics(matches, matches)
    assert out is not None
    assert out["total_matches"] == 2
    assert out["match_wins"] == 1
    assert out["games_won"] == 3
    assert out["games_played"] == 5
    assert out["total_mulligans"] == 3
    assert out["games_with_data"] == 5
    assert out["match_rate"] == 50.0
    assert out["game_rate"] == 60.0
    assert out["mulligan_rate"] == 60.0
    assert out["avg_mulligans_per_match"] == 1.5
    assert out["filtered"] is not None
    assert out["filtered"]["match_total"] == 2


def test_compute_history_metrics_unfiltered_filtered_is_none() -> None:
    matches = [_metric(True, 2, 2, 0)]
    out = compute_history_metrics(matches, [])
    assert out is not None
    assert out["filtered"] is None


def test_compute_history_metrics_zero_games_no_div_by_zero() -> None:
    matches = [_metric(False, 0, 0, 0)]
    out = compute_history_metrics(matches, matches)
    assert out is not None
    assert out["game_rate"] == 0.0
    assert out["mulligan_rate"] == 0.0
    assert out["games_with_data"] == 0
    # Lock in the filtered-branch zero-division guard.
    assert out["filtered"] is not None
    assert out["filtered"]["game_rate"] == 0.0


# --------------------------------------------------------------------- compute_opponent_stats
def test_compute_opponent_stats_empty_returns_none() -> None:
    assert compute_opponent_stats([]) is None


def test_compute_opponent_stats_aggregates() -> None:
    metrics = [
        _metric(True, 2, 3, 1),
        _metric(False, 0, 2, 0),
    ]
    out = compute_opponent_stats(metrics)
    assert out is not None
    assert out["total"] == 2
    assert out["wins"] == 1
    assert out["total_mulligans"] == 1
    assert out["games_played"] == 5
    assert out["win_pct"] == 50.0
    assert out["mull_rate"] == 20.0


# -------------------------------------------------------------------------------- _iter_matches
def test_iter_matches_username_is_player1() -> None:
    mixin = _make_mixin("me")
    raw = [
        {
            "timestamp": datetime(2026, 1, 2, 10, 30),
            "match_score": "2-1",
            "players": ["me", "them"],
            "winner": "me",
            "player1_mulligans": [1, 0],
            "player2_mulligans": [0],
        }
    ]
    out = mixin._iter_matches(raw)
    assert len(out) == 1
    row = out[0]
    assert row["date"] == date(2026, 1, 2)
    assert row["match_win"] is True
    assert row["games_won"] == 2
    assert row["games_total"] == 3
    assert row["total_mulligans"] == 1


def test_iter_matches_username_is_player2_case_insensitive() -> None:
    mixin = _make_mixin("ME")
    raw = [
        {
            "timestamp": datetime(2026, 3, 4, 8, 0),
            # match_score is player1-vs-player2; player2 (us) won 2-0.
            "match_score": "0-2",
            "players": ["them", "me"],
            "winner": "me",
            "player1_mulligans": [0],
            "player2_mulligans": [1, 1],
        }
    ]
    row = mixin._iter_matches(raw)[0]
    # Score is taken from our (player2) perspective: we won 2-0.
    assert row["match_win"] is True
    assert row["games_won"] == 2
    assert row["games_total"] == 2
    assert row["total_mulligans"] == 2


def test_iter_matches_unknown_username_falls_back_to_player1() -> None:
    mixin = _make_mixin("zzz")
    raw = [
        {
            "timestamp": datetime(2026, 5, 6, 12, 0),
            "match_score": "2-0",
            "players": ["a", "b"],
            "winner": "a",
            "total_mulligans": 3,
        }
    ]
    row = mixin._iter_matches(raw)[0]
    # Neither player matches the username: player1 is treated as us, and the
    # aggregate ``total_mulligans`` field is used rather than per-player lists.
    assert row["match_win"] is True
    assert row["games_won"] == 2
    assert row["games_total"] == 2
    assert row["total_mulligans"] == 3


def test_iter_matches_no_username_uses_player1_and_total_mulligans() -> None:
    mixin = _make_mixin(None)
    raw = [
        {
            "timestamp": datetime(2026, 6, 1, 9, 0),
            "match_score": "1-2",
            "players": ["a", "b"],
            "winner": "b",
            "total_mulligans": 4,
        }
    ]
    row = mixin._iter_matches(raw)[0]
    assert row["match_win"] is False
    assert row["games_won"] == 1
    assert row["games_total"] == 3
    assert row["total_mulligans"] == 4


def test_iter_matches_skips_non_dict_entries() -> None:
    mixin = _make_mixin(None)
    out = mixin._iter_matches(["nope", 42, None])  # type: ignore[list-item]
    assert out == []


def test_iter_matches_bad_score_and_missing_fields_default_to_zero() -> None:
    mixin = _make_mixin(None)
    raw = [{"match_score": "??"}]
    row = mixin._iter_matches(raw)[0]
    assert row["date"] is None
    assert row["match_win"] is False
    assert row["games_won"] == 0
    assert row["games_total"] == 0
    assert row["total_mulligans"] == 0


# ----------------------------------------------------------------------------------- _parse_date
def test_parse_date_none_and_empty_return_none() -> None:
    mixin = _make_mixin(None)
    assert mixin._parse_date(None) is None
    assert mixin._parse_date("") is None


def test_parse_date_iso_with_zulu_suffix() -> None:
    mixin = _make_mixin(None)
    assert mixin._parse_date("2026-01-02T10:30:00Z") == date(2026, 1, 2)


def test_parse_date_plain_date() -> None:
    mixin = _make_mixin(None)
    assert mixin._parse_date("2026-01-02") == date(2026, 1, 2)


def test_parse_date_falls_back_to_prefix_parse() -> None:
    mixin = _make_mixin(None)
    # Not valid ISO (space + extra junk), but the first 10 chars are a date.
    assert mixin._parse_date("2026-01-02 something weird") == date(2026, 1, 2)


def test_parse_date_unparseable_returns_none() -> None:
    mixin = _make_mixin(None)
    assert mixin._parse_date("not-a-date") is None


# ---------------------------------------------------------------------------------- _within_range
def test_within_range_none_date_with_no_bounds_included() -> None:
    mixin = _make_mixin(None)
    assert mixin._within_range(None, None, None) is True


def test_within_range_none_date_with_bounds_excluded() -> None:
    mixin = _make_mixin(None)
    assert mixin._within_range(None, date(2026, 1, 1), None) is False
    assert mixin._within_range(None, None, date(2026, 1, 1)) is False


def test_within_range_inside_bounds() -> None:
    mixin = _make_mixin(None)
    assert mixin._within_range(date(2026, 1, 15), date(2026, 1, 1), date(2026, 1, 31)) is True


def test_within_range_before_start_excluded() -> None:
    mixin = _make_mixin(None)
    assert mixin._within_range(date(2025, 12, 31), date(2026, 1, 1), None) is False


def test_within_range_after_end_excluded() -> None:
    mixin = _make_mixin(None)
    assert mixin._within_range(date(2026, 2, 1), None, date(2026, 1, 31)) is False


def test_within_range_boundaries_inclusive() -> None:
    mixin = _make_mixin(None)
    start = date(2026, 1, 1)
    end = date(2026, 1, 31)
    assert mixin._within_range(start, start, end) is True
    assert mixin._within_range(end, start, end) is True
