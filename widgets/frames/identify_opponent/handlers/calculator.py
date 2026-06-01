"""Self-contained hypergeometric calculator handlers for the opponent tracker.

These callbacks have no coupling to opponent tracking; they read the calculator
spin controls and render probabilities into ``calc_result_label``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants import (
    CALC_COPIES_DEFAULT,
    CALC_DECK_SIZE_DEFAULT,
    CALC_DRAWN_DEFAULT,
    CALC_TARGET_DEFAULT,
)
from utils.math_utils import hypergeometric_at_least, hypergeometric_probability

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class CalculatorMixin(_Base):
    """Hypergeometric probability calculator callbacks."""

    def _apply_preset(self, deck_size: int, cards_drawn: int) -> None:
        self.spin_deck_size.SetValue(deck_size)
        self.spin_drawn.SetValue(cards_drawn)
        self._on_calculate(None)

    def _on_calculate(self, _event: wx.CommandEvent | None) -> None:
        try:
            deck_size = self.spin_deck_size.GetValue()
            copies = self.spin_copies.GetValue()
            drawn = self.spin_drawn.GetValue()
            target = self.spin_target.GetValue()

            # Validate inputs
            if copies > deck_size:
                self.calc_result_label.SetLabel("Error: Copies > Deck Size")
                return
            if drawn > deck_size:
                self.calc_result_label.SetLabel("Error: Drawn > Deck Size")
                return
            if target > copies:
                self.calc_result_label.SetLabel("Error: Target > Copies")
                return
            if target > drawn:
                self.calc_result_label.SetLabel("Error: Target > Drawn")
                return

            exact_prob = hypergeometric_probability(deck_size, copies, drawn, target)
            at_least_prob = hypergeometric_at_least(deck_size, copies, drawn, target)

            result_text = (
                f"Exact ({target}): {exact_prob * 100:.2f}%\n"
                f"At least {target}: {at_least_prob * 100:.2f}%"
            )
            self.calc_result_label.SetLabel(result_text)

        except ValueError as e:
            self.calc_result_label.SetLabel(f"Error: {e}")
        except Exception as e:
            logger.error(f"Calculator error: {e}")
            self.calc_result_label.SetLabel("Calculation error")

    def _on_clear_calculator(self, _event: wx.CommandEvent) -> None:
        self.spin_deck_size.SetValue(CALC_DECK_SIZE_DEFAULT)
        self.spin_copies.SetValue(CALC_COPIES_DEFAULT)
        self.spin_drawn.SetValue(CALC_DRAWN_DEFAULT)
        self.spin_target.SetValue(CALC_TARGET_DEFAULT)
        self.calc_result_label.SetLabel("")
