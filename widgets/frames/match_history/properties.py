"""State accessors, i18n helpers, and metrics computation for the match history viewer."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from utils.i18n import translate

if TYPE_CHECKING:
    pass


# --------------------------------------------------------------------------- pure kernels
# The functions below are wx-free and depend only on their arguments so they can
# be unit-tested off-Windows. The mixin methods are thin wrappers around them.


def resolve_match_perspective(
    match: dict[str, Any], current_username: str | None
) -> dict[str, Any]:
    """Resolve a single match from "our" perspective.

    Given a raw match dict and the current username, derive the names,
    archetypes, mulligans and scores for "us" vs the opponent. When the
    username is unknown (or does not match either player), player 1 is
    treated as "us". Pure: no wx, no ``self`` state.
    """
    players = match.get("players", [])
    winner = match.get("winner")

    player1_name = players[0] if len(players) > 0 else "Unknown"
    player2_name = players[1] if len(players) > 1 else "Unknown"
    player1_archetype = match.get("player1_archetype", "Unknown")
    player2_archetype = match.get("player2_archetype", "Unknown")

    match_score_str = match.get("match_score", "?-?")
    try:
        score_parts = match_score_str.split("-")
        player1_score = int(score_parts[0])
        player2_score = int(score_parts[1])
    except (ValueError, IndexError, AttributeError):
        player1_score = 0
        player2_score = 0

    use_player2 = bool(
        current_username
        and player1_name.lower() != current_username.lower()
        and player2_name.lower() == current_username.lower()
    )
    if use_player2:
        our_name = player2_name
        opp_name = player1_name
        our_archetype = player2_archetype
        opp_archetype = player1_archetype
        our_mulligans = match.get("player2_mulligans", [])
        our_score = player2_score
        opp_score = player1_score
    else:
        our_name = player1_name
        opp_name = player2_name
        our_archetype = player1_archetype
        opp_archetype = player2_archetype
        our_mulligans = match.get("player1_mulligans", [])
        our_score = player1_score
        opp_score = player2_score

    return {
        "our_name": our_name,
        "opp_name": opp_name,
        "our_archetype": our_archetype,
        "opp_archetype": opp_archetype,
        "our_mulligans": our_mulligans,
        "our_score": our_score,
        "opp_score": opp_score,
        "we_won": winner == our_name,
    }


#: What an unset format or archetype is shown and filtered as. The parser
#: already writes "Unknown" for an archetype it cannot name; a match whose
#: format could not be detected arrives as ``None`` or an empty string, and
#: both have to land in the same bucket or the dropdown grows two entries that
#: mean the same thing.
UNKNOWN_LABEL = "Unknown"


def normalize_format(value: Any) -> str:
    """Return a match's format as a non-empty display string."""
    text = (value or "").strip() if isinstance(value, str) else ""
    return text or UNKNOWN_LABEL


def filter_match_metrics(
    metrics: list[dict[str, Any]],
    *,
    start: date | None = None,
    end: date | None = None,
    mtg_format: str | None = None,
    our_archetype: str | None = None,
    opp_archetype: str | None = None,
) -> list[dict[str, Any]]:
    """Return the per-match metric dicts passing every supplied constraint.

    One predicate chain rather than one path per filter: the date range was
    already applied inline at the call site, and adding format and archetype
    beside it would otherwise have meant three list comprehensions that each
    have to remember the other two. ``None`` means "no constraint on this
    dimension", so every combination composes.

    Pure: no wx, no ``self`` state.
    """
    selected = list(metrics)
    if start or end:
        selected = [m for m in selected if _date_in_range(m.get("date"), start, end)]
    if mtg_format:
        selected = [m for m in selected if m.get("format") == mtg_format]
    if our_archetype:
        selected = [m for m in selected if m.get("our_archetype") == our_archetype]
    if opp_archetype:
        selected = [m for m in selected if m.get("opp_archetype") == opp_archetype]
    return selected


def _date_in_range(value: date | None, start: date | None, end: date | None) -> bool:
    """Whether *value* falls inside the (optional) range.

    A match with no date is excluded as soon as either bound is set -- it cannot
    be shown to satisfy a range it has no position in.
    """
    if value is None:
        return not (start or end)
    if start and value < start:
        return False
    if end and value > end:
        return False
    return True


def collect_filter_options(metrics: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Return the distinct format / archetype values present, each sorted.

    Only values that actually occur are offered: a Modern-only player is never
    shown a Pauper entry, and never learns the detector has a Vintage bucket it
    would be wrong about. "Unknown" sorts last when present, because it is a
    catch-all rather than a name.
    """

    def _sorted(key: str) -> list[str]:
        values = {str(m.get(key) or UNKNOWN_LABEL) for m in metrics}
        known = sorted(value for value in values if value != UNKNOWN_LABEL)
        return known + ([UNKNOWN_LABEL] if UNKNOWN_LABEL in values else [])

    return {
        "formats": _sorted("format"),
        "our_archetypes": _sorted("our_archetype"),
        "opp_archetypes": _sorted("opp_archetype"),
    }


def compute_history_metrics(
    matches: list[dict[str, Any]], filtered: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Compute aggregate history metrics from per-match metric dicts.

    ``matches`` and ``filtered`` are lists of the dicts produced by
    :meth:`MatchHistoryPropertiesMixin._iter_matches`. Returns ``None`` when
    ``matches`` is empty (nothing to display). Pure: no wx, no ``self`` state.
    """
    if not matches:
        return None

    total_matches = len(matches)
    match_wins = sum(1 for match in matches if match["match_win"])
    games_won = sum(match["games_won"] for match in matches)
    games_played = sum(match["games_total"] for match in matches)

    total_mulligans = sum(match["total_mulligans"] for match in matches)
    games_with_data = sum(match["games_total"] for match in matches if match["games_total"] > 0)
    mulligan_rate = (total_mulligans / games_with_data * 100) if games_with_data else 0.0
    avg_mulligans_per_match = total_mulligans / total_matches if total_matches else 0.0

    match_rate = (match_wins / total_matches) * 100 if total_matches else 0.0
    game_rate = (games_won / games_played) * 100 if games_played else 0.0

    result: dict[str, Any] = {
        "total_matches": total_matches,
        "match_wins": match_wins,
        "games_won": games_won,
        "games_played": games_played,
        "total_mulligans": total_mulligans,
        "games_with_data": games_with_data,
        "mulligan_rate": mulligan_rate,
        "avg_mulligans_per_match": avg_mulligans_per_match,
        "match_rate": match_rate,
        "game_rate": game_rate,
        "filtered": None,
    }

    if filtered:
        filtered_match_wins = sum(1 for match in filtered if match["match_win"])
        filtered_games_won = sum(match["games_won"] for match in filtered)
        filtered_games_total = sum(match["games_total"] for match in filtered)
        filtered_match_rate = (filtered_match_wins / len(filtered)) * 100
        filtered_game_rate = (
            (filtered_games_won / filtered_games_total) * 100 if filtered_games_total else 0.0
        )
        result["filtered"] = {
            "match_wins": filtered_match_wins,
            "match_total": len(filtered),
            "games_won": filtered_games_won,
            "games_total": filtered_games_total,
            "match_rate": filtered_match_rate,
            "game_rate": filtered_game_rate,
        }

    return result


def compute_opponent_stats(metrics: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Aggregate per-match metric dicts into opponent win/mulligan stats.

    ``metrics`` is a list of the dicts produced by
    :meth:`MatchHistoryPropertiesMixin._iter_matches`, already filtered to a
    single opponent. Returns ``None`` when empty. Pure: no wx, no ``self`` state.
    """
    if not metrics:
        return None

    total = len(metrics)
    wins = sum(1 for m in metrics if m["match_win"])
    total_mulls = sum(m["total_mulligans"] for m in metrics)
    games_played = sum(m["games_total"] for m in metrics)
    win_pct = (wins / total * 100) if total else 0.0
    mull_rate = (total_mulls / games_played * 100) if games_played else 0.0

    return {
        "total": total,
        "wins": wins,
        "total_mulligans": total_mulls,
        "games_played": games_played,
        "win_pct": win_pct,
        "mull_rate": mull_rate,
    }


class MatchHistoryPropertiesMixin:
    """Getters, state setters, and pure-data helpers for :class:`MatchHistoryFrame`.

    Kept as a mixin (no ``__init__``) so :class:`MatchHistoryFrame` remains the
    single source of truth for instance-state initialization.
    """

    _locale: str | None
    current_username: str | None
    history_items: list[dict[str, Any]]

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    def _set_username(self, username: str | None) -> None:
        from loguru import logger

        if username and username != self.current_username:
            self.current_username = username
            logger.debug(f"Set current username: {username}")
            if self.history_items:
                self._populate_history(self.history_items)
        else:
            self.current_username = username
            logger.debug(f"Set current username: {username}")

    def _get_opponent_name(self, match_data: dict[str, Any]) -> str | None:
        return match_data.get("_opp_name") or None

    def _iter_matches(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for match in items:
            if not isinstance(match, dict):
                continue

            timestamp = match.get("timestamp")
            date_obj = timestamp.date() if timestamp else None

            score = match.get("match_score", "0-0")
            try:
                player1_score, player2_score = map(int, score.split("-"))
            except (ValueError, AttributeError):
                player1_score, player2_score = 0, 0

            players = match.get("players", [])
            winner = match.get("winner")

            if self.current_username:
                if players and players[0].lower() == self.current_username.lower():
                    our_name = players[0]
                    our_mulligans = sum(match.get("player1_mulligans", []))
                    our_score = player1_score
                    opp_score = player2_score
                elif (
                    players
                    and len(players) > 1
                    and players[1].lower() == self.current_username.lower()
                ):
                    our_name = players[1]
                    our_mulligans = sum(match.get("player2_mulligans", []))
                    our_score = player2_score
                    opp_score = player1_score
                else:
                    our_name = players[0] if len(players) > 0 else None
                    our_mulligans = match.get("total_mulligans", 0)
                    our_score = player1_score
                    opp_score = player2_score
            else:
                our_name = players[0] if len(players) > 0 else None
                our_mulligans = match.get("total_mulligans", 0)
                our_score = player1_score
                opp_score = player2_score

            match_win = (winner == our_name) if winner and our_name else False

            # The three filter dimensions travel with the metrics rather than
            # being re-derived downstream: ``filter_match_metrics`` is pure and
            # is handed these dicts, not the raw matches.
            perspective = resolve_match_perspective(match, self.current_username)

            results.append(
                {
                    "date": date_obj,
                    "match_win": match_win,
                    "games_won": our_score,
                    "games_total": our_score + opp_score,
                    "total_mulligans": our_mulligans,
                    "format": normalize_format(match.get("format")),
                    "our_archetype": perspective["our_archetype"] or UNKNOWN_LABEL,
                    "opp_archetype": perspective["opp_archetype"] or UNKNOWN_LABEL,
                    "opponent": perspective["opp_name"],
                }
            )

        return results

    def _parse_date(self, value: str | None) -> date | None:
        if not value:
            return None
        try:
            if value.endswith("Z"):
                value = value.replace("Z", "+00:00")
            return datetime.fromisoformat(value).date()
        except ValueError:
            try:
                return datetime.strptime(value[:10], "%Y-%m-%d").date()
            except ValueError:
                return None

    def _parse_date_input(self, value: str) -> date | None:
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            self._set_busy(False, self._t("match.status.invalid_date"))
            return None

    def _within_range(self, date_obj: date | None, start: date | None, end: date | None) -> bool:
        """Thin wrapper: the rule itself lives in :func:`_date_in_range`.

        Kept so the two date bounds have one implementation now that
        :func:`filter_match_metrics` applies them too.
        """
        return _date_in_range(date_obj, start, end)
