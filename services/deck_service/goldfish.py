"""Goldfishing a decklist: shuffle it, look at seven cards, put them on a table.

"Goldfishing" is playing a deck against no opponent. Issue #1045 asks for the
deckbuilding half of it -- the thing every other deckbuilder has and this one did
not: shuffle the mainboard, see what a real opening hand off this list looks
like, draw another, mulligan, and lay the cards out on a table so the curve reads
as a board rather than as a bar chart.

Everything here is wx-free on purpose. The panel in
:mod:`widgets.panels.deck_goldfish_panel` owns the pixels and the mouse and
nothing else, so the shuffling, the mulligan bookkeeping and the table state are
testable without a display -- and the shuffle is seedable, so a test can assert
on an exact hand instead of on a distribution.

There are no game rules in here, deliberately (#1045: "no rules parsing
mechanics, just let the player place any card from hand and tap it"). Any card
can be put on the table, land or not; tapping is a marker the *player* sets, and
nothing untaps at the start of anything. The one piece of Magic that is modelled
is the London mulligan's bottoming count, because "how many would I have to put
back" is most of what a mulligan hand is worth looking at -- and even that is
reported (:attr:`GoldfishTable.cards_to_bottom`) rather than enforced.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from services.deck_service.parser import DeckParser

#: Cards in an opening hand. Not ``STATS_HAND_SIZE``: that constant is the
#: sample size of the Deck Stats tab's hypergeometric land curve, which happens
#: to be seven for the same reason but is a statistics parameter, not the number
#: of pieces of cardboard this deals.
OPENING_HAND_SIZE = 7


def build_library(deck_text: str) -> list[str]:
    """Expand a decklist's **mainboard** into one entry per physical card.

    Order is the decklist's own; :meth:`GoldfishTable.new_hand` shuffles. The
    sideboard is left out because a goldfish is a game one, and a 75-card
    library would quietly make every opening hand wrong.
    """
    analysis = DeckParser().analyze_deck(deck_text)
    library: list[str] = []
    for name, count in analysis["mainboard_cards"]:
        # Averaged decklists carry fractional counts (see DeckAverager); a
        # physical library cannot, so they round down to whole copies.
        library.extend([name] * max(0, int(count)))
    return library


@dataclass
class TableCard:
    """One card the player has put down, and where they put it.

    ``x`` and ``y`` are fractions of the table's width and height rather than
    pixels: the panel is resizable, and a card dropped in the middle of the
    table should still be in the middle after the window is widened.
    """

    name: str
    x: float = 0.0
    y: float = 0.0
    tapped: bool = False


class GoldfishTable:
    """The whole goldfish: a shuffled library, a hand, and a table to play onto.

    The RNG is injectable so tests get an exact, repeatable shuffle; the app
    leaves it alone and gets :mod:`random`'s default seeding.
    """

    def __init__(
        self,
        deck_text: str = "",
        *,
        seed: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._rng = rng if rng is not None else random.Random(seed)
        self._deck: list[str] = []
        self._library: list[str] = []
        self._hand: list[str] = []
        self._table: list[TableCard] = []
        self._mulligans = 0
        self.set_deck(deck_text)

    # ----- read surface -----
    @property
    def deck_size(self) -> int:
        """Cards in the mainboard this was built from."""
        return len(self._deck)

    @property
    def library_size(self) -> int:
        return len(self._library)

    @property
    def hand(self) -> tuple[str, ...]:
        return tuple(self._hand)

    @property
    def table(self) -> tuple[TableCard, ...]:
        return tuple(self._table)

    @property
    def mulligans(self) -> int:
        return self._mulligans

    @property
    def cards_to_bottom(self) -> int:
        """London mulligan: one card to the bottom per mulligan taken.

        Capped at the hand size so a seventh mulligan reads as "bottom all
        seven" rather than as a negative keep.
        """
        return min(self._mulligans, OPENING_HAND_SIZE)

    @property
    def has_dealt(self) -> bool:
        """Whether a hand has been dealt since the last :meth:`set_deck`.

        What the panel shows before the first deal is a prompt, not an empty
        table, and "the hand is empty" cannot tell those apart -- a player who
        has put all seven cards down has an empty hand too.
        """
        return self._dealt

    # ----- deck -----
    def set_deck(self, deck_text: str) -> None:
        """Point the goldfish at a decklist, discarding any game in progress.

        Called on every deck load, so it does no shuffling and deals no cards:
        the tab may never be opened, and a deck load is already the app's
        heaviest synchronous moment (see ``docs/perf/deck-load-profile.md``).
        """
        self._deck = build_library(deck_text)
        self._library = []
        self._hand = []
        self._table = []
        self._mulligans = 0
        self._dealt = False

    # ----- dealing -----
    def new_hand(self) -> tuple[str, ...]:
        """Shuffle everything back together and deal a fresh, un-mulliganed seven."""
        self._mulligans = 0
        return self._deal()

    def mulligan(self) -> tuple[str, ...]:
        """Shuffle back and deal seven again, counting one more mulligan.

        The seven are dealt in full and nothing is bottomed here: which cards a
        London mulligan puts back is the decision the player is goldfishing to
        practise, so the count is reported and the choice is theirs.
        """
        self._mulligans += 1
        return self._deal()

    def draw(self, count: int = 1) -> tuple[str, ...]:
        """Draw up to ``count`` cards. Returns what was actually drawn.

        Short of a full draw when the library runs out -- a goldfish has no
        loss condition, so decking is just the end of the cards.
        """
        drawn: list[str] = []
        for _ in range(max(0, count)):
            if not self._library:
                break
            drawn.append(self._library.pop())
        self._hand.extend(drawn)
        return tuple(drawn)

    def _deal(self) -> tuple[str, ...]:
        self._library = list(self._deck)
        self._rng.shuffle(self._library)
        self._hand = []
        self._table = []
        self._dealt = True
        self.draw(OPENING_HAND_SIZE)
        return tuple(self._hand)

    # ----- the table -----
    def play(self, index: int, x: float = 0.0, y: float = 0.0) -> TableCard | None:
        """Put the hand card at ``index`` onto the table at ``(x, y)``.

        Returns the placed card, or ``None`` for an index that is not in hand --
        a click can land on a card the previous click already played.
        """
        if not 0 <= index < len(self._hand):
            return None
        card = TableCard(name=self._hand.pop(index), x=_clamp(x), y=_clamp(y))
        self._table.append(card)
        return card

    def move(self, index: int, x: float, y: float) -> bool:
        """Drag a table card to ``(x, y)``. False if there is no such card."""
        if not 0 <= index < len(self._table):
            return False
        card = self._table[index]
        card.x = _clamp(x)
        card.y = _clamp(y)
        # Dragged cards come to the front: a card the player just moved is the
        # one they are looking at, and on a crowded table it would otherwise
        # slide back under whatever was played after it.
        self._table.append(self._table.pop(index))
        return True

    def toggle_tap(self, index: int) -> bool:
        """Tap or untap the table card at ``index``. Returns its new state."""
        if not 0 <= index < len(self._table):
            return False
        card = self._table[index]
        card.tapped = not card.tapped
        return card.tapped

    def return_to_hand(self, index: int) -> bool:
        """Take a table card back into hand, untapped. False if there is none."""
        if not 0 <= index < len(self._table):
            return False
        self._hand.append(self._table.pop(index).name)
        return True


def _clamp(value: float) -> float:
    """Keep a table position inside the table."""
    return min(1.0, max(0.0, float(value)))
