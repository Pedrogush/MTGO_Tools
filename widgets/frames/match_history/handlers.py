"""Event and worker callbacks for the match history viewer."""

from __future__ import annotations

import threading
from typing import Any

import wx
import wx.dataview as dv
from loguru import logger

from widgets.frames.match_history.properties import (
    compute_history_metrics,
    compute_opponent_stats,
    resolve_match_perspective,
)


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
            username = self.controller.get_current_username()
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
                matches = self.controller.parse_all_gamelogs(
                    limit=None, progress_callback=progress_callback
                )
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
            self.current_username = self.controller.infer_username_from_matches(matches)
            if self.current_username:
                logger.debug(f"Using inferred username: {self.current_username}")

        for match in matches:
            if not isinstance(match, dict):
                continue

            timestamp = match.get("timestamp")
            date_str = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "Unknown"

            perspective = resolve_match_perspective(match, self.current_username)
            our_name = perspective["our_name"]
            opp_name = perspective["opp_name"]
            our_archetype = perspective["our_archetype"]
            opp_archetype = perspective["opp_archetype"]
            our_mulligans = perspective["our_mulligans"]
            our_score = perspective["our_score"]
            opp_score = perspective["opp_score"]
            we_won = perspective["we_won"]

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

        stats = compute_opponent_stats(self._iter_matches(matches))
        if not stats:
            self._clear_opp_stats()
            return

        self.opp_match_rate_label.SetLabel(
            f"Vs. {opp_name} Match Win Rate: {stats['win_pct']:.1f}%"
            f" ({stats['wins']}/{stats['total']})"
        )
        self.opp_mull_rate_label.SetLabel(
            f"Vs. {opp_name} Mull Rate: {stats['mull_rate']:.1f}%"
            f" ({stats['total_mulligans']}/{stats['games_played']} games)"
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

        start = self._parse_date_input(self.start_date_ctrl.GetValue())
        end = self._parse_date_input(self.end_date_ctrl.GetValue())
        if start or end:
            filtered = [match for match in matches if self._within_range(match["date"], start, end)]
        else:
            filtered = matches

        metrics = compute_history_metrics(matches, filtered)

        self.match_rate_label.SetLabel(
            f"{self._t('match.metrics.abs_match_rate')}: {metrics['match_rate']:.1f}%"
            f" ({metrics['match_wins']}/{metrics['total_matches']})"
        )
        self.game_rate_label.SetLabel(
            f"{self._t('match.metrics.abs_game_rate')}: {metrics['game_rate']:.1f}%"
            f" ({metrics['games_won']}/{metrics['games_played'] or 1})"
        )
        self.mulligan_rate_label.SetLabel(
            f"{self._t('match.metrics.mulligan_rate')}: {metrics['mulligan_rate']:.1f}%"
            f" ({metrics['total_mulligans']}/{metrics['games_with_data']} games)"
        )
        self.avg_mulligans_label.SetLabel(
            f"{self._t('match.metrics.avg_mulligans')}: {metrics['avg_mulligans_per_match']:.2f}"
        )

        filtered_metrics = metrics["filtered"]
        if filtered_metrics:
            self.filtered_match_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_match_rate')}:"
                f" {filtered_metrics['match_rate']:.1f}%"
                f" ({filtered_metrics['match_wins']}/{filtered_metrics['match_total']})"
            )
            self.filtered_game_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_game_rate')}:"
                f" {filtered_metrics['game_rate']:.1f}%"
                f" ({filtered_metrics['games_won']}/{filtered_metrics['games_total']})"
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
