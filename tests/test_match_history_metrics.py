"""Tests for the wx-free compute kernels of the match history viewer.

These cover the pure functions extracted from
``widgets/frames/match_history/handlers.py`` into ``properties.py``:
``resolve_match_perspective``, ``compute_history_metrics`` and
``compute_opponent_stats``. ``wx`` is not importable in the WSL dev
environment and the package ``__init__`` pulls in the wx-dependent frame, so
``properties.py`` is loaded directly by file path.
"""

from __future__ import annotations

import importlib.util
import types
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
