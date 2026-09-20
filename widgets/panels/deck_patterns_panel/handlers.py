"""Computing and rendering the Patterns tab.

The analysis runs on the app's background worker rather than on the UI thread.
A deck of many land profiles can take a visible moment at turn 6-7, and §2.4
asks for that not to be paid by a frozen window. Each run carries a token; a
result whose token is stale is dropped, which is what stops a slow run from
overwriting the answer to a newer deck.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import wx
from loguru import logger

from services.deck_patterns_service import PatternsResult

if TYPE_CHECKING:
    from widgets.panels.deck_patterns_panel.protocol import DeckPatternsPanelProto

    _Base = DeckPatternsPanelProto
else:
    _Base = object


class DeckPatternsPanelHandlersMixin(_Base):
    """Recompute/render behaviour for :class:`DeckPatternsPanel`.

    Kept as a mixin (no ``__init__``) so the panel stays the single source of
    truth for instance-state initialization.
    """

    # ------------------------------------------------------------------ input ------------------------------------------------------------------
    def set_zone_cards(self, zone_cards: dict[str, list[dict[str, Any]]]) -> None:
        """Take a new decklist. Recomputes only while the tab is visible."""
        self.zone_cards = zone_cards or {}
        self._dirty = True
        if self.IsShownOnScreen():
            self.recompute()

    def on_shown(self) -> None:
        """Called when the tab becomes visible: compute what was deferred."""
        if self._dirty and not self._pending:
            self.recompute()

    def selected_turn(self) -> int:
        index = self.turn_choice.GetSelection()
        if index == wx.NOT_FOUND:
            return 1
        return index + 1

    # ------------------------------------------------------------------ events ------------------------------------------------------------------
    def on_turn_changed(self, _event: wx.CommandEvent) -> None:
        self.render()

    def on_refresh(self, _event: wx.CommandEvent) -> None:
        self._dirty = True
        self.recompute()

    # ------------------------------------------------------------------ compute ------------------------------------------------------------------
    def recompute(self) -> None:
        """Kick off an analysis run for the current decklist."""
        entries = list(self.zone_cards.get("main", []))
        if not entries:
            self._result = None
            self._dirty = False
            self.render()
            return

        self._run_token += 1
        token = self._run_token
        self._pending = True
        self.status_label.SetLabel(self._t("patterns.status.computing"))

        options = self.options

        def work() -> PatternsResult:
            return self.patterns_service.analyse(entries, options=options)

        def done(result: PatternsResult) -> None:
            if token != self._run_token:
                return  # a newer run has started; this answer is stale
            self._result = result
            self._pending = False
            self._dirty = False
            self.render()

        def failed(exc: Exception) -> None:
            if token != self._run_token:
                return
            logger.warning(f"Patterns analysis failed: {exc}")
            self._result = None
            self._pending = False
            self._dirty = False
            self.status_label.SetLabel(self._t("patterns.status.failed"))
            self.tree.DeleteAllItems()

        if self.worker is None:
            # No worker (tests, or a panel built standalone): run inline.
            try:
                done(work())
            except Exception as exc:  # noqa: BLE001
                failed(exc)
            return

        self.worker.submit(work, on_success=done, on_error=failed)

    # ------------------------------------------------------------------ render ------------------------------------------------------------------
    def render(self) -> None:
        """Draw the selected turn's combinations and their maximal plays."""
        self.tree.DeleteAllItems()
        result = self._result

        if result is None:
            self.status_label.SetLabel(
                self._t("patterns.status.computing")
                if self._pending
                else self._t("patterns.status.no_deck")
            )
            return

        turn_number = self.selected_turn()
        turn = result.turn(turn_number)
        root = self.tree.AddRoot("patterns")

        if turn is None or not turn.combinations:
            self.status_label.SetLabel(self._t("patterns.status.no_lands"))
            return

        for combination in turn.combinations:
            label = self._t(
                "patterns.combination",
                lands=combination.label,
                mana=combination.combination.total_mana,
            )
            node = self.tree.AppendItem(root, label)
            if not combination.plays:
                self.tree.AppendItem(node, self._t("patterns.no_plays"))
                continue
            for play in combination.plays:
                self.tree.AppendItem(node, play.as_text())
            self.tree.Expand(node)

        self.status_label.SetLabel(self._summary(turn))

    def _summary(self, turn: Any) -> str:
        base = self._t(
            "patterns.status.summary",
            turn=turn.turn,
            combinations=len(turn.combinations),
            playable=turn.playable_count,
        )
        if turn.truncated:
            return f"{base} — {self._t('patterns.status.truncated')}"
        return base
