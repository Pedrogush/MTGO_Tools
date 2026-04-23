"""Event and worker callbacks for the match history viewer."""

from __future__ import annotations

import threading
from typing import Any

import wx
import wx.dataview as dv
from loguru import logger

from utils.gamelog_parser import infer_username_from_matches, parse_all_gamelogs


class MatchHistoryHandlersMixin:
    """Callbacks and worker-thread bridges for :class:`MatchHistoryFrame`."""

    # Attributes supplied by :class:`MatchHistoryFrame` / the properties mixin.
    history_items: list[dict[str, Any]]
    current_username: str | None
    tree: Any
    refresh_button: wx.Button
    status_label: wx.StaticText
    match_rate_label: wx.StaticText
    game_rate_label: wx.StaticText
    filtered_match_rate_label: wx.StaticText
    filtered_game_rate_label: wx.StaticText
    mulligan_rate_label: wx.StaticText
    avg_mulligans_label: wx.StaticText
    opp_match_rate_label: wx.StaticText
    opp_mull_rate_label: wx.StaticText
    start_date_ctrl: wx.TextCtrl
    end_date_ctrl: wx.TextCtrl

    # ------------------------------------------------------------------ worker bootstraps
    def _init_username(self) -> None:
        def worker() -> None:
            from utils.gamelog_parser import get_current_username

            username = get_current_username()
            wx.CallAfter(self._set_username, username)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_history(self) -> None:
        if not self or not self.IsShown():
            return
        self._set_busy(True, self._t("match.status.loading"))

        def progress_callback(current: int, total: int) -> None:
            wx.CallAfter(
                self._set_busy,
                True,
                self._t("match.status.parsing", current=current, total=total),
            )

        def worker() -> None:
            try:
                matches = parse_all_gamelogs(limit=None, progress_callback=progress_callback)
                logger.debug("Loaded {} matches from GameLog files", len(matches))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to load match history from GameLogs")
                wx.CallAfter(self._handle_history_error, str(exc))
                return
            wx.CallAfter(self._populate_history, matches)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_history_error(self, message: str) -> None:  # noqa: ARG002 - logged by worker
        if not self or not self.IsShown():
            return
        self._set_busy(False, self._t("match.status.failed"))

    def _populate_history(self, matches: list[dict[str, Any]]) -> None:
        if not self or not self.IsShown():
            return

        self.tree.DeleteAllItems()
        root = self.tree.GetRootItem()

        if not matches:
            self._set_busy(False, self._t("match.status.no_data"))
            return

        self.history_items = matches

        if not self.current_username:
            self.current_username = infer_username_from_matches(matches)
            if self.current_username:
                logger.debug(f"Using inferred username: {self.current_username}")

        for match in matches:
            if not isinstance(match, dict):
                continue

            players = match.get("players", [])
            winner = match.get("winner")
            match_score_str = match.get("match_score", "?-?")
            timestamp = match.get("timestamp")
            date_str = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "Unknown"

            player1_name = players[0] if len(players) > 0 else "Unknown"
            player2_name = players[1] if len(players) > 1 else "Unknown"
            player1_archetype = match.get("player1_archetype", "Unknown")
            player2_archetype = match.get("player2_archetype", "Unknown")

            try:
                score_parts = match_score_str.split("-")
                player1_score = int(score_parts[0])
                player2_score = int(score_parts[1])
            except (ValueError, IndexError):
                player1_score = 0
                player2_score = 0

            if self.current_username:
                if player1_name.lower() == self.current_username.lower():
                    our_name = player1_name
                    opp_name = player2_name
                    our_archetype = player1_archetype
                    opp_archetype = player2_archetype
                    our_mulligans = match.get("player1_mulligans", [])
                    our_score = player1_score
                    opp_score = player2_score
                else:
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

            we_won = winner == our_name

            total_mulls = sum(our_mulligans) if our_mulligans else 0
            mull_detail = ", ".join(str(m) for m in our_mulligans) if our_mulligans else "0"

            result_text = self._t("match.result.won") if we_won else self._t("match.result.lost")
            result_display = f"{result_text} {our_score}-{opp_score}"

            label = f"{our_name} ({our_archetype}) vs {opp_name} ({opp_archetype})"

            item = self.tree.AppendItem(root, label)
            self.tree.SetItemText(item, 1, result_display)
            self.tree.SetItemText(item, 2, f"{total_mulls} ({mull_detail})")
            self.tree.SetItemText(item, 3, date_str)

            # Cache the resolved opponent so on_item_selected can look it up without
            # re-deriving it (avoids misidentification when current_username is None
            # and player order is ambiguous).
            match["_opp_name"] = opp_name

            self.tree.SetItemData(item, match)

        self._set_busy(False, self._t("match.status.loaded", count=len(matches)))
        self._update_metrics()
        self._clear_opp_stats()

    # ------------------------------------------------------------------ tree events
    def on_item_activated(self, event: dv.TreeListEvent) -> None:
        item = event.GetItem()
        if not item.IsOk():
            return

        match_data = self.tree.GetItemData(item)
        if not match_data:
            return

        player1_deck = match_data.get("player1_deck", [])
        player2_deck = match_data.get("player2_deck", [])
        player1_archetype = match_data.get("player1_archetype", "Unknown")
        player2_archetype = match_data.get("player2_archetype", "Unknown")
        players = match_data.get("players", [])
        player1_name = players[0] if len(players) > 0 else "Player 1"
        player2_name = players[1] if len(players) > 1 else "Player 2"

        deck_text = f"=== {player1_name} ({player1_archetype}) — {len(player1_deck)} cards ===\n"
        deck_text += "\n".join(f"  • {card}" for card in player1_deck)
        deck_text += (
            f"\n\n=== {player2_name} ({player2_archetype}) — {len(player2_deck)} cards ===\n"
        )
        deck_text += "\n".join(f"  • {card}" for card in player2_deck)

        dlg = wx.MessageDialog(self, deck_text, "Deck Lists", wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()

    def on_item_selected(self, event: dv.TreeListEvent) -> None:
        item = event.GetItem()
        if not item.IsOk():
            self._clear_opp_stats()
            return

        match_data = self.tree.GetItemData(item)
        if not match_data:
            self._clear_opp_stats()
            return

        opp_name = self._get_opponent_name(match_data)
        if not opp_name:
            self._clear_opp_stats()
            return

        self._update_opp_stats(opp_name)

    # ------------------------------------------------------------------ status / stats
    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        if not self:
            return
        if self.refresh_button:
            self.refresh_button.Enable(not busy)
        if message:
            self.status_label.SetLabel(message)
        elif busy:
            self.status_label.SetLabel(self._t("research.loading_archetypes"))
        else:
            self.status_label.SetLabel(self._t("app.status.ready"))

    def _update_opp_stats(self, opp_name: str) -> None:
        matches = [
            m for m in self.history_items if isinstance(m, dict) and m.get("_opp_name") == opp_name
        ]
        if not matches:
            self._clear_opp_stats()
            return

        metrics = self._iter_matches(matches)
        total = len(metrics)
        wins = sum(1 for m in metrics if m["match_win"])
        total_mulls = sum(m["total_mulligans"] for m in metrics)
        games_played = sum(m["games_total"] for m in metrics)
        win_pct = (wins / total * 100) if total else 0.0
        mull_rate = (total_mulls / games_played * 100) if games_played else 0.0

        self.opp_match_rate_label.SetLabel(
            f"Vs. {opp_name} Match Win Rate: {win_pct:.1f}% ({wins}/{total})"
        )
        self.opp_mull_rate_label.SetLabel(
            f"Vs. {opp_name} Mull Rate: {mull_rate:.1f}%" f" ({total_mulls}/{games_played} games)"
        )

    def _clear_opp_stats(self) -> None:
        self.opp_match_rate_label.SetLabel(f"{self._t('match.metrics.opp_match_rate')}: \u2014")
        self.opp_mull_rate_label.SetLabel(f"{self._t('match.metrics.opp_mull_rate')}: \u2014")

    def _update_metrics(self) -> None:
        matches = self._iter_matches(self.history_items)
        if not matches:
            self.match_rate_label.SetLabel(f"{self._t('match.metrics.abs_match_rate')}: \u2014")
            self.game_rate_label.SetLabel(f"{self._t('match.metrics.abs_game_rate')}: \u2014")
            self.filtered_match_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_match_rate')}: \u2014"
            )
            self.filtered_game_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_game_rate')}: \u2014"
            )
            self.mulligan_rate_label.SetLabel(f"{self._t('match.metrics.mulligan_rate')}: \u2014")
            self.avg_mulligans_label.SetLabel(f"{self._t('match.metrics.avg_mulligans')}: \u2014")
            return

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

        self.match_rate_label.SetLabel(
            f"{self._t('match.metrics.abs_match_rate')}: {match_rate:.1f}%"
            f" ({match_wins}/{total_matches})"
        )
        self.game_rate_label.SetLabel(
            f"{self._t('match.metrics.abs_game_rate')}: {game_rate:.1f}%"
            f" ({games_won}/{games_played or 1})"
        )
        self.mulligan_rate_label.SetLabel(
            f"{self._t('match.metrics.mulligan_rate')}: {mulligan_rate:.1f}%"
            f" ({total_mulligans}/{games_with_data} games)"
        )
        self.avg_mulligans_label.SetLabel(
            f"{self._t('match.metrics.avg_mulligans')}: {avg_mulligans_per_match:.2f}"
        )

        start = self._parse_date_input(self.start_date_ctrl.GetValue())
        end = self._parse_date_input(self.end_date_ctrl.GetValue())
        if start or end:
            filtered = [match for match in matches if self._within_range(match["date"], start, end)]
        else:
            filtered = matches

        if filtered:
            filtered_match_wins = sum(1 for match in filtered if match["match_win"])
            filtered_games_won = sum(match["games_won"] for match in filtered)
            filtered_games_total = sum(match["games_total"] for match in filtered)
            filtered_match_rate = (filtered_match_wins / len(filtered)) * 100
            filtered_game_rate = (
                (filtered_games_won / filtered_games_total) * 100 if filtered_games_total else 0.0
            )
            self.filtered_match_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_match_rate')}: {filtered_match_rate:.1f}%"
                f" ({filtered_match_wins}/{len(filtered)})"
            )
            self.filtered_game_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_game_rate')}: {filtered_game_rate:.1f}%"
                f" ({filtered_games_won}/{filtered_games_total})"
            )
        else:
            self.filtered_match_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_match_rate')}: \u2014"
            )
            self.filtered_game_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_game_rate')}: \u2014"
            )

    # ------------------------------------------------------------------ lifecycle
    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()
