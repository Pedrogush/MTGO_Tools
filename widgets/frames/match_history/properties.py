"""State accessors, i18n helpers, and metrics computation for the match history viewer."""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from utils.i18n import translate

if TYPE_CHECKING:
    pass


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

            results.append(
                {
                    "date": date_obj,
                    "match_win": match_win,
                    "games_won": our_score,
                    "games_total": our_score + opp_score,
                    "total_mulligans": our_mulligans,
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
        if date_obj is None:
            return False if start or end else True
        if start and date_obj < start:
            return False
        if end and date_obj > end:
            return False
        return True
