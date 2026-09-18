"""Public API and button handling for the goldfish panel.

The deal itself is cheap -- one ``list`` copy, one ``random.shuffle`` of sixty
strings and seven pops, measured well under a millisecond -- so it runs inline on
the UI thread and is wrapped in a :func:`~utils.perf.perf_phase` so it shows up
in the same profile the rest of the deck workspace does. The expensive part,
decoding card art, is already off-thread in
:mod:`widgets.panels.deck_goldfish_panel.card_art`.

Note what :meth:`set_deck` does *not* do: deal. It is called from the app
frame's ``_update_stats`` on every deck load, and the deck-render block already
runs ~315-385 ms synchronously (``docs/perf/deck-load-profile.md``). A tab the
user may never open must not add to it, so loading a deck only re-points the
table and the first hand is dealt when the player asks for one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.perf import perf_phase

if TYPE_CHECKING:
    from widgets.panels.deck_goldfish_panel.protocol import DeckGoldfishPanelProto

    _Base = DeckGoldfishPanelProto
else:
    _Base = object


class DeckGoldfishPanelHandlersMixin(_Base):
    """Deck loading, the three toolbar actions, and the status line."""

    # ----- public API -----
    def set_deck(self, deck_text: str) -> None:
        """Point the goldfish at the loaded decklist, ending any hand in progress.

        Deliberately does not deal; see this module's docstring.
        """
        self.table.set_deck(deck_text)
        self._view.refresh_table()
        self._refresh_status()

    def clear(self) -> None:
        """No deck is loaded any more."""
        self.set_deck("")

    # ----- toolbar -----
    def _on_new_hand(self, _event: wx.CommandEvent) -> None:
        self._deal(self.table.new_hand)

    def _on_mulligan(self, _event: wx.CommandEvent) -> None:
        self._deal(self.table.mulligan)

    def _on_draw(self, _event: wx.CommandEvent) -> None:
        self.table.draw()
        self._view.refresh_table()
        self._refresh_status()

    def _deal(self, deal) -> None:
        with perf_phase("goldfish: shuffle + deal"):
            deal()
        # Every card in the fresh hand is a decode candidate; queueing them all
        # at once lets the pool work while the player is still reading the first.
        self._art.prefetch(list(self.table.hand))
        self._view.refresh_table()
        self._refresh_status()

    # ----- status -----
    def _refresh_status(self) -> None:
        """Restate the library/hand/mulligan counts and re-enable the toolbar.

        Also the ``on_change`` the table view calls after every gesture: playing
        a card moves it out of the hand, and the hand count is on this line.
        """
        table = self.table
        has_deck = table.deck_size > 0
        if not has_deck:
            self.status_label.SetLabel(self._t("tabs.goldfish.no_deck"))
        elif not table.has_dealt:
            self.status_label.SetLabel(self._t("tabs.goldfish.ready", deck=table.deck_size))
        else:
            status = self._t(
                "tabs.goldfish.status",
                library=table.library_size,
                hand=len(table.hand),
            )
            if table.mulligans:
                status += self._t(
                    "tabs.goldfish.status.mulligans",
                    mulligans=table.mulligans,
                    bottom=table.cards_to_bottom,
                )
            self.status_label.SetLabel(status)
        # Mulliganing or drawing before there is a deck (or before the first
        # hand) has no meaning, and a button that does nothing is worse than one
        # that says it cannot.
        self.new_hand_button.Enable(has_deck)
        self.mulligan_button.Enable(has_deck and table.has_dealt)
        self.draw_button.Enable(has_deck and table.has_dealt and table.library_size > 0)

    def _on_art_ready(self, name: str) -> None:
        self._view.on_art_ready(name)
