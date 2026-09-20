"""Patterns tab command handlers: turn selection and the computed readout.

A screenshot of the tree shows that rows rendered; it cannot show that the
*right* land combinations were enumerated or that a play list is complete.
``deck_patterns`` reports the same structure the tree is built from, so a script
can assert the analysis against a hand-checked expectation and leave the
screenshot to prove it drew.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class DeckPatternsMixin(_Base):
    """Read and drive the deck capability explorer."""

    def _patterns_panel(self) -> Any:
        return getattr(self.frame, "deck_patterns_panel", None)

    def _handle_deck_patterns(self, turn: int | None = None) -> dict[str, Any]:
        """The selected turn's combinations and maximal plays, as computed."""
        panel = self._patterns_panel()
        if panel is None:
            return {"error": "Patterns panel not built"}

        if turn is not None:
            index = int(turn) - 1
            if index < 0 or index >= panel.turn_choice.GetCount():
                return {"error": f"Turn {turn} out of range"}
            panel.turn_choice.SetSelection(index)
            panel.render()

        result = panel._result
        if result is None:
            return {
                "pending": bool(panel._pending),
                "turn": panel.selected_turn(),
                "combinations": [],
                "status": panel.status_label.GetLabel(),
            }

        selected = panel.selected_turn()
        turn_result = result.turn(selected)
        return {
            "pending": bool(panel._pending),
            "turn": selected,
            "max_turn": result.max_turn,
            "truncated": bool(turn_result.truncated) if turn_result else False,
            "status": panel.status_label.GetLabel(),
            "land_groups": [
                {
                    "label": group.label,
                    "count": group.count,
                    "produces": sorted(group.production.options),
                    "amount": group.production.amount,
                }
                for group in result.land_groups
            ],
            "cache_hits": result.cache_hits,
            "cache_misses": result.cache_misses,
            "combinations": [
                {
                    "lands": combination.label,
                    "mana": combination.combination.total_mana,
                    "plays": [play.as_text() for play in combination.plays],
                }
                for combination in (turn_result.combinations if turn_result else ())
            ],
        }

    def _handle_deck_patterns_refresh(self) -> dict[str, Any]:
        """Force a recompute for the deck currently loaded."""
        panel = self._patterns_panel()
        if panel is None:
            return {"error": "Patterns panel not built"}
        panel._dirty = True
        panel.recompute()
        return {"triggered": True, "pending": bool(panel._pending)}
