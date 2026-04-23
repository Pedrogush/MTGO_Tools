"""wxPython match history viewer backed by GameLog parsing."""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

import threading
from datetime import datetime
from typing import Any

import wx
import wx.dataview as dv
from loguru import logger

from utils.gamelog_parser import infer_username_from_matches, parse_all_gamelogs
from utils.i18n import translate

DARK_BG = wx.Colour(20, 22, 27)
DARK_PANEL = wx.Colour(34, 39, 46)
DARK_ALT = wx.Colour(40, 46, 54)
LIGHT_TEXT = wx.Colour(236, 236, 236)
SUBDUED_TEXT = wx.Colour(185, 191, 202)


class MatchHistoryFrame(wx.Frame):
    """Simple window displaying recent MTGO matches grouped by event."""

    _FIXED_WIDTH = 850
    _COL_WIDTHS = [100, 90, 140]  # Result, Mulligans, Date (pixels)

    def __init__(self, parent: wx.Window | None = None, locale: str | None = None) -> None:
        style = wx.DEFAULT_FRAME_STYLE | wx.STAY_ON_TOP
        super().__init__(
            parent,
            title=translate(locale, "window.title.match_history"),
            size=(self._FIXED_WIDTH, 460),
            style=style,
        )
        self._locale = locale
        # Lock horizontal size; allow vertical resize only
        self.SetSizeHints(self._FIXED_WIDTH, 300, self._FIXED_WIDTH, -1)

        self.history_items: list[dict[str, Any]] = []
        self.start_filter: str | None = None
        self.end_filter: str | None = None
        self.current_username: str | None = None

        self._build_ui()
        self.Centre(wx.BOTH)
        self.Bind(wx.EVT_SIZE, self._on_frame_size)

        self.Bind(wx.EVT_CLOSE, self.on_close)
        wx.CallAfter(self._fit_tree_columns)
        wx.CallAfter(self._init_username)
        wx.CallAfter(self.refresh_history)

    def _init_username(self) -> None:

        def worker():
            from utils.gamelog_parser import get_current_username

            username = get_current_username()
            wx.CallAfter(self._set_username, username)

        threading.Thread(target=worker, daemon=True).start()

    def _set_username(self, username: str | None) -> None:
        if username and username != self.current_username:
            self.current_username = username
            logger.debug(f"Set current username: {username}")
            if self.history_items:
                # Re-render so player perspective is corrected now that we know who we are
                self._populate_history(self.history_items)
        else:
            self.current_username = username
            logger.debug(f"Set current username: {username}")

    def _t(self, key: str, **kwargs: object) -> str:
        return translate(self._locale, key, **kwargs)

    # ------------------------------------------------------------------ UI ------------------------------------------------------------------
    def _build_ui(self) -> None:
        panel = wx.Panel(self)
        panel.SetBackgroundColour(DARK_BG)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        toolbar = wx.BoxSizer(wx.HORIZONTAL)
        sizer.Add(toolbar, 0, wx.ALL | wx.EXPAND, 10)

        self.refresh_button = wx.Button(panel, label=self._t("match.btn.refresh"))
        self._stylize_button(self.refresh_button)
        self.refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self.refresh_history())
        toolbar.Add(self.refresh_button, 0)

        toolbar.AddStretchSpacer(1)

        self.status_label = wx.StaticText(panel, label=self._t("app.status.ready"))
        self.status_label.SetForegroundColour(SUBDUED_TEXT)
        toolbar.Add(self.status_label, 0, wx.ALIGN_CENTER_VERTICAL)

        metrics_box = wx.StaticBox(panel, label=self._t("match.metrics.title"))
        metrics_box.SetForegroundColour(LIGHT_TEXT)
        metrics_box.SetBackgroundColour(DARK_PANEL)
        metrics_sizer = wx.StaticBoxSizer(metrics_box, wx.VERTICAL)
        box_parent = metrics_sizer.GetStaticBox()
        sizer.Add(metrics_sizer, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 6)

        metrics_inner = wx.BoxSizer(wx.VERTICAL)
        metrics_sizer.Add(metrics_inner, 0, wx.EXPAND | wx.ALL, 8)

        row1 = wx.BoxSizer(wx.HORIZONTAL)
        self.match_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.abs_match_rate')}: \u2014"
        )
        self.match_rate_label.SetForegroundColour(LIGHT_TEXT)
        row1.Add(self.match_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.game_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.abs_game_rate')}: \u2014"
        )
        self.game_rate_label.SetForegroundColour(LIGHT_TEXT)
        row1.Add(self.game_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row1, 0, wx.EXPAND | wx.BOTTOM, 4)

        row2 = wx.BoxSizer(wx.HORIZONTAL)
        self.filtered_match_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.filtered_match_rate')}: \u2014"
        )
        self.filtered_match_rate_label.SetForegroundColour(LIGHT_TEXT)
        row2.Add(self.filtered_match_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.filtered_game_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.filtered_game_rate')}: \u2014"
        )
        self.filtered_game_rate_label.SetForegroundColour(LIGHT_TEXT)
        row2.Add(self.filtered_game_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row2, 0, wx.EXPAND | wx.BOTTOM, 4)

        row3 = wx.BoxSizer(wx.HORIZONTAL)
        self.mulligan_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.mulligan_rate')}: \u2014"
        )
        self.mulligan_rate_label.SetForegroundColour(LIGHT_TEXT)
        row3.Add(self.mulligan_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.avg_mulligans_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.avg_mulligans')}: \u2014"
        )
        self.avg_mulligans_label.SetForegroundColour(LIGHT_TEXT)
        row3.Add(self.avg_mulligans_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row3, 0, wx.EXPAND)

        metrics_inner.Add(wx.StaticLine(box_parent), 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 6)

        row_opp = wx.BoxSizer(wx.HORIZONTAL)
        self.opp_match_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.opp_match_rate')}: \u2014"
        )
        self.opp_match_rate_label.SetForegroundColour(SUBDUED_TEXT)
        row_opp.Add(self.opp_match_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        self.opp_mull_rate_label = wx.StaticText(
            box_parent, label=f"{self._t('match.metrics.opp_mull_rate')}: \u2014"
        )
        self.opp_mull_rate_label.SetForegroundColour(SUBDUED_TEXT)
        row_opp.Add(self.opp_mull_rate_label, 1, wx.ALIGN_CENTER_VERTICAL)
        metrics_inner.Add(row_opp, 0, wx.EXPAND)

        filter_row = wx.BoxSizer(wx.HORIZONTAL)
        metrics_sizer.Add(filter_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 6)
        filter_row.Add(
            wx.StaticText(box_parent, label=self._t("match.filter.start")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            4,
        )
        self.start_date_ctrl = wx.TextCtrl(box_parent, size=(120, -1))
        self.start_date_ctrl.SetBackgroundColour(DARK_ALT)
        self.start_date_ctrl.SetForegroundColour(LIGHT_TEXT)
        filter_row.Add(self.start_date_ctrl, 0, wx.RIGHT, 10)
        filter_row.Add(
            wx.StaticText(box_parent, label=self._t("match.filter.end")),
            0,
            wx.ALIGN_CENTER_VERTICAL | wx.RIGHT,
            4,
        )
        self.end_date_ctrl = wx.TextCtrl(box_parent, size=(120, -1))
        self.end_date_ctrl.SetBackgroundColour(DARK_ALT)
        self.end_date_ctrl.SetForegroundColour(LIGHT_TEXT)
        filter_row.Add(self.end_date_ctrl, 0, wx.RIGHT, 10)
        apply_btn = wx.Button(box_parent, label=self._t("match.filter.apply"))
        apply_btn.Bind(wx.EVT_BUTTON, lambda _evt: self._update_metrics())
        filter_row.Add(apply_btn, 0)
        filter_row.AddStretchSpacer(1)

        self.tree = dv.TreeListCtrl(panel, style=dv.TL_DEFAULT_STYLE | dv.TL_SINGLE)
        self.tree.SetBackgroundColour(DARK_ALT)
        self.tree.AppendColumn(self._t("match.col.players"), width=380)
        self.tree.AppendColumn(self._t("match.col.result"), width=100)
        self.tree.AppendColumn(self._t("match.col.mulligans"), width=90)
        self.tree.AppendColumn(self._t("match.col.date"), width=140)
        self.tree.Bind(dv.EVT_TREELIST_ITEM_ACTIVATED, self.on_item_activated)
        self.tree.Bind(dv.EVT_TREELIST_SELECTION_CHANGED, self.on_item_selected)
        sizer.Add(self.tree, 1, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, 10)

    def _on_frame_size(self, event: wx.SizeEvent) -> None:
        event.Skip()
        wx.CallAfter(self._fit_tree_columns)

    def _fit_tree_columns(self) -> None:
        if not self.tree:
            return
        dv_ctrl = self.tree.GetDataView()
        tree_w = self.tree.GetClientSize().width
        scrollbar_w = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        # Column 0 in the DataViewCtrl is the internal tree-expander column;
        # our first user column (Players) is at index 1.
        expander_w = dv_ctrl.GetColumn(0).GetWidth()
        col0_w = tree_w - expander_w - sum(self._COL_WIDTHS) - scrollbar_w
        if col0_w > 80:
            dv_ctrl.GetColumn(1).SetWidth(col0_w)

    def _stylize_button(self, button: wx.Button) -> None:
        button.SetBackgroundColour(DARK_PANEL)
        button.SetForegroundColour(LIGHT_TEXT)
        font = button.GetFont()
        font.MakeBold()
        button.SetFont(font)

    # ------------------------------------------------------------------ Data loading ---------------------------------------------------------
    def refresh_history(self) -> None:
        if not self or not self.IsShown():
            return
        self._set_busy(True, self._t("match.status.loading"))

        def progress_callback(current: int, total: int) -> None:
            wx.CallAfter(
                self._set_busy, True, self._t("match.status.parsing", current=current, total=total)
            )

        def worker() -> None:
            try:
                # Parse ALL GameLog files (no limit)
                matches = parse_all_gamelogs(limit=None, progress_callback=progress_callback)

                logger.debug("Loaded {} matches from GameLog files", len(matches))
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to load match history from GameLogs")
                wx.CallAfter(self._handle_history_error, str(exc))
                return
            wx.CallAfter(self._populate_history, matches)

        threading.Thread(target=worker, daemon=True).start()

    def _handle_history_error(self, message: str) -> None:
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

        # Fall back to inferring who the local user is when the bridge is offline
        if not self.current_username:
            self.current_username = infer_username_from_matches(matches)
            if self.current_username:
                logger.debug(f"Using inferred username: {self.current_username}")

        for match in matches:
            if not isinstance(match, dict):
                continue

            # Extract match data
            players = match.get("players", [])
            winner = match.get("winner")
            match_score_str = match.get("match_score", "?-?")
            timestamp = match.get("timestamp")
            date_str = timestamp.strftime("%Y-%m-%d %H:%M") if timestamp else "Unknown"

            # Get player names and archetypes
            player1_name = players[0] if len(players) > 0 else "Unknown"
            player2_name = players[1] if len(players) > 1 else "Unknown"
            player1_archetype = match.get("player1_archetype", "Unknown")
            player2_archetype = match.get("player2_archetype", "Unknown")

            # Parse the match score
            try:
                score_parts = match_score_str.split("-")
                player1_score = int(score_parts[0])
                player2_score = int(score_parts[1])
            except (ValueError, IndexError):
                player1_score = 0
                player2_score = 0

            # Determine which player is us
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
                # Assume player 1 is us
                our_name = player1_name
                opp_name = player2_name
                our_archetype = player1_archetype
                opp_archetype = player2_archetype
                our_mulligans = match.get("player1_mulligans", [])
                our_score = player1_score
                opp_score = player2_score

            # Determine if we won
            we_won = winner == our_name

            # Format mulligan display
            total_mulls = sum(our_mulligans) if our_mulligans else 0
            mull_detail = ", ".join(str(m) for m in our_mulligans) if our_mulligans else "0"

            # Format result - score from OUR perspective (our score - opponent score)
            result_text = self._t("match.result.won") if we_won else self._t("match.result.lost")
            result_display = f"{result_text} {our_score}-{opp_score}"

            # Format player display
            label = f"{our_name} ({our_archetype}) vs {opp_name} ({opp_archetype})"

            # Create tree item
            item = self.tree.AppendItem(root, label)
            self.tree.SetItemText(item, 1, result_display)
            self.tree.SetItemText(item, 2, f"{total_mulls} ({mull_detail})")
            self.tree.SetItemText(item, 3, date_str)

            # Cache the resolved opponent so on_item_selected can look it up
            # without re-deriving it (avoids misidentification when
            # current_username is None and player order is ambiguous).
            match["_opp_name"] = opp_name

            # Store full match data in item
            self.tree.SetItemData(item, match)

        self._set_busy(False, self._t("match.status.loaded", count=len(matches)))
        self._update_metrics()
        self._clear_opp_stats()

    def on_item_activated(self, event: dv.TreeListEvent) -> None:
        item = event.GetItem()
        if not item.IsOk():
            return

        match_data = self.tree.GetItemData(item)
        if not match_data:
            return

        # Format deck list
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

        # Show in dialog
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

    def _get_opponent_name(self, match_data: dict[str, Any]) -> str | None:
        # Use the name that was resolved during _populate_history, where the
        # current_username / player-perspective logic already ran correctly.
        return match_data.get("_opp_name") or None

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

    # ------------------------------------------------------------------ Metrics ---------------------------------------------------------------
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

        # Calculate mulligan statistics
        total_mulligans = sum(match["total_mulligans"] for match in matches)
        games_with_data = sum(match["games_total"] for match in matches if match["games_total"] > 0)
        mulligan_rate = (total_mulligans / games_with_data * 100) if games_with_data else 0.0
        avg_mulligans_per_match = total_mulligans / total_matches if total_matches else 0.0

        match_rate = (match_wins / total_matches) * 100 if total_matches else 0.0
        game_rate = (games_won / games_played) * 100 if games_played else 0.0

        self.match_rate_label.SetLabel(
            f"{self._t('match.metrics.abs_match_rate')}: {match_rate:.1f}% ({match_wins}/{total_matches})"
        )
        self.game_rate_label.SetLabel(
            f"{self._t('match.metrics.abs_game_rate')}: {game_rate:.1f}% ({games_won}/{games_played or 1})"
        )
        self.mulligan_rate_label.SetLabel(
            f"{self._t('match.metrics.mulligan_rate')}: {mulligan_rate:.1f}% ({total_mulligans}/{games_with_data} games)"
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
                f"{self._t('match.metrics.filtered_match_rate')}: {filtered_match_rate:.1f}% ({filtered_match_wins}/{len(filtered)})"
            )
            self.filtered_game_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_game_rate')}: {filtered_game_rate:.1f}% ({filtered_games_won}/{filtered_games_total})"
            )
        else:
            self.filtered_match_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_match_rate')}: \u2014"
            )
            self.filtered_game_rate_label.SetLabel(
                f"{self._t('match.metrics.filtered_game_rate')}: \u2014"
            )

    def _iter_matches(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for match in items:
            if not isinstance(match, dict):
                continue

            # Extract data from new format
            timestamp = match.get("timestamp")
            date_obj = timestamp.date() if timestamp else None

            # Parse match score (e.g., "2-1")
            score = match.get("match_score", "0-0")
            try:
                player1_score, player2_score = map(int, score.split("-"))
            except (ValueError, AttributeError):
                player1_score, player2_score = 0, 0

            # Determine if we won and get our scores
            players = match.get("players", [])
            winner = match.get("winner")

            # Determine which player is us
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

    def _parse_date(self, value: str | None):
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

    def _parse_date_input(self, value: str):
        value = value.strip()
        if not value:
            return None
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError:
            self._set_busy(False, self._t("match.status.invalid_date"))
            return None

    def _within_range(self, date_obj, start, end) -> bool:
        if date_obj is None:
            return False if start or end else True
        if start and date_obj < start:
            return False
        if end and date_obj > end:
            return False
        return True

    # ------------------------------------------------------------------ Lifecycle -------------------------------------------------------------
    def on_close(self, event: wx.CloseEvent) -> None:
        event.Skip()


def main() -> None:
    """Launch the match history viewer as a standalone application."""
    from utils.constants import LOGS_DIR, ensure_base_dirs
    from utils.logging_config import configure_logging

    ensure_base_dirs()
    log_file = configure_logging(LOGS_DIR)
    if log_file:
        logger.info(f"Writing logs to {log_file}")

    app = wx.App(False)
    frame = MatchHistoryFrame()
    frame.Show()
    app.MainLoop()


if __name__ == "__main__":
    main()


__all__ = ["MatchHistoryFrame"]
