"""The Goldfish tab's three behaviours that only exist once there is a window.

The game state and the geometry are covered wx-free in ``tests/test_goldfish.py``.
What is left needs a real panel with a real client size, and it is exactly the
part a review of the first cut asked to be changed:

* opening the tab deals. The tab has nothing on it but a hand, so making the
  player press *New hand* to see one was a button standing in front of the
  feature;
* the cards are measured from the panel. A fixed card size left the fan floating
  in the middle of a wide tab with unresolved space either side of it, and any
  fix that stretches a card to fill that space is worse than the gap;
* a played card can be dragged back into the hand. Dragging is how a card gets
  onto the table, so dragging has to be how it comes off -- right-click alone
  makes the table a one-way drop.
"""

from __future__ import annotations

import pytest
import wx

from widgets.panels.deck_goldfish_panel import DeckGoldfishPanel
from widgets.panels.deck_goldfish_panel.card_art import GoldfishArtCache
from widgets.panels.deck_goldfish_panel.layout import card_metrics

DECK_TEXT = """4 Colossus Hammer
4 Sigarda's Aid
4 Puresteel Paladin
4 Stoneforge Mystic
4 Lightning Greaves
4 Giver of Runes
4 Esper Sentinel
4 Urza's Saga
4 Inkmoth Nexus
4 Ancient Tomb
20 Plains

3 Damping Sphere
"""

#: Big enough that the hand fan has room to be wrong in -- the old fixed-size
#: fan left roughly a third of this width blank.
PANEL_SIZE = (1200, 800)


class _Mouse:
    """The two methods the table view asks a ``wx.MouseEvent`` for."""

    def __init__(self, x: int, y: int, *, dragging: bool = False) -> None:
        self._position = wx.Point(x, y)
        self._dragging = dragging

    def GetPosition(self) -> wx.Point:  # noqa: N802 - wx's spelling
        return self._position

    def Dragging(self) -> bool:  # noqa: N802 - wx's spelling
        return self._dragging

    def Skip(self) -> None:  # noqa: N802 - wx's spelling
        pass


@pytest.fixture(name="goldfish_panel")
def fixture_goldfish_panel(wx_app):
    """A panel with a seeded shuffle and no art on disk.

    ``get_card_image`` returning ``None`` is the placeholder path, which is what
    every assertion here wants: the sizes below are the layout's, not a
    particular JPEG's.
    """
    frame = wx.Frame(None, size=PANEL_SIZE)
    panel = DeckGoldfishPanel(
        frame,
        get_card_image=lambda _name, _size: None,
        get_metadata=lambda _name: None,
        seed=1045,
    )
    frame.SetClientSize(PANEL_SIZE)
    frame.Layout()
    yield panel
    frame.Destroy()


def _view_metrics(panel: DeckGoldfishPanel):
    size = panel._view.GetClientSize()
    return card_metrics(size.GetWidth(), size.GetHeight())


def _drag(panel: DeckGoldfishPanel, start: wx.Point, end: wx.Point) -> None:
    """Press on ``start``, travel to ``end``, release. The whole gesture."""
    view = panel._view
    view._on_left_down(_Mouse(start.x, start.y))
    view._on_motion(_Mouse(end.x, end.y, dragging=True))
    view._on_left_up(_Mouse(end.x, end.y))


# ---------------------------------------------------------------------------
# Opening the tab deals
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("wx_app")
class TestTheFirstHandDealsItself:
    def test_showing_the_tab_deals_a_hand(self, goldfish_panel) -> None:
        goldfish_panel.set_deck(DECK_TEXT)
        assert not goldfish_panel.table.has_dealt, "loading a deck must stay off this path"

        goldfish_panel.on_shown()

        assert goldfish_panel.table.has_dealt
        assert len(goldfish_panel.table.hand) == 7

    def test_coming_back_to_the_tab_leaves_the_board_alone(self, goldfish_panel) -> None:
        """The player left it half played out on purpose."""
        goldfish_panel.set_deck(DECK_TEXT)
        goldfish_panel.on_shown()
        goldfish_panel.table.play(0, 0.5, 0.5)
        before = (goldfish_panel.table.hand, goldfish_panel.table.table)

        goldfish_panel.on_shown()

        assert (goldfish_panel.table.hand, goldfish_panel.table.table) == before

    def test_an_empty_tab_with_no_deck_deals_nothing(self, goldfish_panel) -> None:
        goldfish_panel.on_shown()

        assert not goldfish_panel.table.has_dealt
        assert goldfish_panel.table.hand == ()

    def test_a_deck_arriving_under_an_open_tab_still_gets_a_hand(self, goldfish_panel) -> None:
        """Opened before any deck was loaded, then a deck loads: the workspace
        calls ``notify_deck_tab_shown`` after ``set_deck`` for exactly this."""
        goldfish_panel.on_shown()
        goldfish_panel.set_deck(DECK_TEXT)

        goldfish_panel.on_shown()

        assert len(goldfish_panel.table.hand) == 7


# ---------------------------------------------------------------------------
# The cards are measured from the panel
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("wx_app")
class TestCardsFillTheWidthWithoutStretching:
    def test_a_full_hand_reaches_both_edges_of_the_strip(self, goldfish_panel) -> None:
        from widgets.panels.deck_goldfish_panel.layout import hand_boxes, split_regions

        goldfish_panel.set_deck(DECK_TEXT)
        goldfish_panel.on_shown()
        size = goldfish_panel._view.GetClientSize()
        metrics = _view_metrics(goldfish_panel)
        _table_region, hand_region = split_regions(size.GetWidth(), size.GetHeight(), metrics)

        boxes = hand_boxes(7, hand_region, metrics)

        assert boxes[0].x == hand_region.x
        assert boxes[-1].x + boxes[-1].width == hand_region.x + hand_region.width

    def test_art_is_drawn_at_the_panel_s_card_size(self, goldfish_panel) -> None:
        metrics = _view_metrics(goldfish_panel)
        art = GoldfishArtCache(lambda _n, _s: None, lambda _n: None, lambda _n: None)

        bitmap = art.bitmap("Colossus Hammer", metrics)

        assert (bitmap.GetWidth(), bitmap.GetHeight()) == (metrics.width, metrics.height)

    def test_a_face_is_never_scaled_up_from_a_smaller_decode(self, goldfish_panel) -> None:
        """The blur this replaced: a face decoded once at a fixed width and
        rescaled to the panel's. A size change must re-decode, not re-scale."""
        art = GoldfishArtCache(lambda _n, _s: None, lambda _n: None, lambda _n: None)
        small = card_metrics(700, 500)

        art.bitmap("Colossus Hammer", small)
        generation = art._generation
        art.bitmap("Colossus Hammer", card_metrics(1600, 1000))

        assert art._generation > generation, "a size change must start a new decode"
        assert art._loaded == set(), "nothing is 'loaded' at the new size yet"

    def test_a_tapped_card_is_the_same_card_on_its_side(self, goldfish_panel) -> None:
        """Not a separately sized card: the tapped face's edges are the upright
        one's, swapped. Anything else would be a stretched card."""
        metrics = _view_metrics(goldfish_panel)
        art = GoldfishArtCache(lambda _n, _s: None, lambda _n: None, lambda _n: None)

        tapped = art.bitmap("Colossus Hammer", metrics, tapped=True)

        assert (tapped.GetWidth(), tapped.GetHeight()) == (metrics.height, metrics.width)

    def test_resizing_the_panel_rescales_the_faces(self, goldfish_panel) -> None:
        art = GoldfishArtCache(lambda _n, _s: None, lambda _n: None, lambda _n: None)
        small = card_metrics(700, 500)
        large = card_metrics(1600, 1000)

        art.bitmap("Colossus Hammer", small)
        regrown = art.bitmap("Colossus Hammer", large)

        assert large.width > small.width, "the fixture sizes must actually differ"
        assert regrown.GetWidth() == large.width


# ---------------------------------------------------------------------------
# A played card can be dragged back
# ---------------------------------------------------------------------------
@pytest.mark.usefixtures("wx_app")
class TestDraggingACardBackIntoTheHand:
    def _played_card_centre(self, panel: DeckGoldfishPanel) -> wx.Point:
        from widgets.panels.deck_goldfish_panel.layout import split_regions, table_box

        size = panel._view.GetClientSize()
        metrics = _view_metrics(panel)
        table_region, _hand = split_regions(size.GetWidth(), size.GetHeight(), metrics)
        card = panel.table.table[0]
        box = table_box(card.x, card.y, card.tapped, table_region, metrics)
        return wx.Point(box.x + box.width // 2, box.y + box.height // 2)

    def _hand_strip_point(self, panel: DeckGoldfishPanel) -> wx.Point:
        from widgets.panels.deck_goldfish_panel.layout import split_regions

        size = panel._view.GetClientSize()
        metrics = _view_metrics(panel)
        _table, hand_region = split_regions(size.GetWidth(), size.GetHeight(), metrics)
        return wx.Point(hand_region.x + hand_region.width // 2, hand_region.y + 4)

    def test_a_card_dragged_onto_the_hand_strip_comes_back(self, goldfish_panel) -> None:
        goldfish_panel.set_deck(DECK_TEXT)
        goldfish_panel.on_shown()
        goldfish_panel.table.play(0, 0.5, 0.5)
        played = goldfish_panel.table.table[0].name

        _drag(
            goldfish_panel,
            self._played_card_centre(goldfish_panel),
            self._hand_strip_point(goldfish_panel),
        )

        assert goldfish_panel.table.table == ()
        assert played in goldfish_panel.table.hand

    def test_it_comes_back_untapped(self, goldfish_panel) -> None:
        goldfish_panel.set_deck(DECK_TEXT)
        goldfish_panel.on_shown()
        goldfish_panel.table.play(0, 0.5, 0.5)
        goldfish_panel.table.toggle_tap(0)

        _drag(
            goldfish_panel,
            self._played_card_centre(goldfish_panel),
            self._hand_strip_point(goldfish_panel),
        )
        hand_size = len(goldfish_panel.table.hand)
        goldfish_panel.table.play(hand_size - 1, 0.5, 0.5)

        assert not goldfish_panel.table.table[0].tapped

    def test_a_drag_that_stays_on_the_table_still_just_moves_the_card(self, goldfish_panel) -> None:
        """The new gesture must not swallow the old one."""
        goldfish_panel.set_deck(DECK_TEXT)
        goldfish_panel.on_shown()
        goldfish_panel.table.play(0, 0.2, 0.2)
        start = self._played_card_centre(goldfish_panel)

        _drag(goldfish_panel, start, wx.Point(start.x + 120, start.y + 60))

        assert len(goldfish_panel.table.table) == 1
        assert goldfish_panel.table.table[0].x > 0.2

    def test_a_click_without_travel_is_still_a_tap(self, goldfish_panel) -> None:
        goldfish_panel.set_deck(DECK_TEXT)
        goldfish_panel.on_shown()
        goldfish_panel.table.play(0, 0.5, 0.5)
        centre = self._played_card_centre(goldfish_panel)
        view = goldfish_panel._view

        view._on_left_down(_Mouse(centre.x, centre.y))
        view._on_left_up(_Mouse(centre.x, centre.y))

        assert goldfish_panel.table.table[0].tapped
