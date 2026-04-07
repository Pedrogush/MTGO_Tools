from collections.abc import Callable
from typing import Any

import wx
import wx.lib.scrolledpanel as scrolled

from utils.constants import DARK_PANEL, DECK_CARD_WIDTH, SUBDUED_TEXT
from utils.mana_icon_factory import ManaIconFactory
from utils.perf import timed
from widgets.panels.card_box_panel import CardBoxPanel

_EMPTY_STATE_HEADING_SIZE = 13
_EMPTY_STATE_HINT_SIZE = 10
_EMPTY_STATE_HEADING_GAP = 6

_ZONE_EMPTY_HEADING = {
    "main": "No deck loaded",
    "side": "Sideboard is empty",
    "out": "No cards out",
}
_ZONE_EMPTY_HINT = {
    "main": "Select a deck from the list, or load one from file",
}


class CardTablePanel(wx.Panel):
    GRID_COLUMNS = 4
    GRID_GAP = 8
    POOL_SIZE = 60

    def __init__(
        self,
        parent: wx.Window,
        zone: str,
        icon_factory: ManaIconFactory,
        get_metadata: Callable[[str], dict[str, Any] | None],
        owned_status: Callable[[str, int], tuple[str, tuple[int, int, int]]],
        on_delta: Callable[[str, str, int], None],
        on_remove: Callable[[str, str], None],
        on_add: Callable[[str], None],
        on_select: Callable[[str, dict[str, Any] | None], None],
        on_hover: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.zone = zone
        self.icon_factory = icon_factory
        self._get_metadata = get_metadata
        self._owned_status = owned_status
        self._on_delta = on_delta
        self._on_remove = on_remove
        self._on_add = on_add
        self._on_select = on_select
        self._on_hover = on_hover
        self.cards: list[dict[str, Any]] = []
        self.card_widgets: list[CardBoxPanel] = []
        self._pool: list[CardBoxPanel] = []
        self.active_panel: CardBoxPanel | None = None
        self.selected_name: str | None = None

        self.SetBackgroundColour(DARK_PANEL)
        outer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(outer)

        header = wx.BoxSizer(wx.HORIZONTAL)
        self.count_label = wx.StaticText(self, label="0 cards")
        self.count_label.SetForegroundColour(SUBDUED_TEXT)
        header.Add(self.count_label, 0, wx.ALIGN_CENTER_VERTICAL)
        header.AddStretchSpacer(1)
        outer.Add(header, 0, wx.EXPAND | wx.BOTTOM, 4)

        # Content area switches between an empty-state hint and the card grid.
        self._content_book = wx.Simplebook(self)
        self._content_book.SetBackgroundColour(DARK_PANEL)

        self._empty_state = self._build_empty_state(self._content_book, zone)
        self._content_book.AddPage(self._empty_state, "empty")

        self.scroller = scrolled.ScrolledPanel(self._content_book, style=wx.VSCROLL)
        self.scroller.SetBackgroundColour(DARK_PANEL)
        self.grid_sizer = wx.WrapSizer(wx.HORIZONTAL)

        # Pre-create POOL_SIZE panels. Visible panels show cards; hidden panels
        # are excluded from layout via sizer.Show(panel, False).
        for _ in range(self.POOL_SIZE):
            cell = CardBoxPanel(
                self.scroller,
                zone,
                {"name": "", "qty": 0},
                icon_factory,
                get_metadata,
                owned_status,
                on_delta,
                on_remove,
                self._handle_card_click,
                on_hover,
            )
            self.grid_sizer.Add(cell, 0, wx.RIGHT | wx.BOTTOM, self.GRID_GAP)
            self.grid_sizer.Show(cell, False)
            self._pool.append(cell)

        self.scroller.SetSizer(self.grid_sizer)
        self.scroller.SetupScrolling(scroll_x=False, scroll_y=True, rate_x=5, rate_y=5)
        self._content_book.AddPage(self.scroller, "cards")

        self._loading_state = self._build_loading_state(self._content_book)
        self._content_book.AddPage(self._loading_state, "loading")

        outer.Add(self._content_book, 1, wx.EXPAND)

    @staticmethod
    def _build_loading_state(parent: wx.Window) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        sizer.AddStretchSpacer(2)
        label = wx.StaticText(panel, label="")
        label.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
        label.SetFont(
            wx.Font(
                _EMPTY_STATE_HEADING_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
        )
        sizer.Add(label, 0, wx.ALIGN_CENTER_HORIZONTAL)
        sizer.AddStretchSpacer(3)
        panel._label = label  # type: ignore[attr-defined]
        return panel

    def show_loading(self, label: str) -> None:
        self._loading_state._label.SetLabel(label)  # type: ignore[attr-defined]
        if self._content_book.GetSelection() != 2:
            self._content_book.ChangeSelection(2)

    @staticmethod
    def _build_empty_state(parent: wx.Window, zone: str) -> wx.Panel:
        panel = wx.Panel(parent)
        panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        panel.SetSizer(sizer)

        heading_text = _ZONE_EMPTY_HEADING.get(zone, "")
        hint_text = _ZONE_EMPTY_HINT.get(zone, "")

        sizer.AddStretchSpacer(2)

        if heading_text:
            heading = wx.StaticText(panel, label=heading_text)
            heading.SetForegroundColour(wx.Colour(*SUBDUED_TEXT))
            heading_font = wx.Font(
                _EMPTY_STATE_HEADING_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
            heading.SetFont(heading_font)
            sizer.Add(
                heading,
                0,
                wx.ALIGN_CENTER_HORIZONTAL | wx.BOTTOM,
                _EMPTY_STATE_HEADING_GAP,
            )

        if hint_text:
            hint = wx.StaticText(panel, label=hint_text)
            hint.SetForegroundColour(wx.Colour(*(max(c - 40, 0) for c in SUBDUED_TEXT)))
            hint_font = wx.Font(
                _EMPTY_STATE_HINT_SIZE,
                wx.FONTFAMILY_SWISS,
                wx.FONTSTYLE_NORMAL,
                wx.FONTWEIGHT_NORMAL,
            )
            hint.SetFont(hint_font)
            sizer.Add(hint, 0, wx.ALIGN_CENTER_HORIZONTAL)

        sizer.AddStretchSpacer(3)
        return panel

    @classmethod
    def grid_width(cls) -> int:
        scrollbar_width = wx.SystemSettings.GetMetric(wx.SYS_VSCROLL_X)
        if scrollbar_width <= 0:
            scrollbar_width = 16
        # Each panel has GRID_GAP right-border, so effective width per column is
        # DECK_CARD_WIDTH + GRID_GAP. The scroller must be wide enough for exactly
        # GRID_COLUMNS panels plus the vertical scrollbar.
        return (DECK_CARD_WIDTH + cls.GRID_GAP) * cls.GRID_COLUMNS + scrollbar_width

    def set_cards(self, cards: list[dict[str, Any]], preserve_scroll: bool = False) -> None:
        self.cards = cards
        self._update_panels(cards, preserve_scroll)

    @timed
    def _update_panels(self, cards: list[dict[str, Any]], preserve_scroll: bool = False) -> None:
        self.Freeze()
        needs_image_load: list[CardBoxPanel] = []
        try:
            self.scroller.Freeze()
            try:
                if self.active_panel:
                    self.active_panel.set_active(False)
                self.active_panel = None
                total = lands = mdfcs = 0
                for card in cards:
                    qty = card["qty"]
                    total += qty
                    meta = self._get_metadata(card["name"]) or {}
                    type_line = (meta.get("type_line") or "").lower()
                    back_type_line = (meta.get("back_type_line") or "").lower()
                    if "land" in type_line:
                        lands += qty
                    elif "land" in back_type_line:
                        mdfcs += qty
                label = f"{total} card{'s' if total != 1 else ''}"
                parts = []
                if lands:
                    parts.append(f"{lands} land{'s' if lands != 1 else ''}")
                if mdfcs:
                    parts.append(f"{mdfcs} MDFC{'s' if mdfcs != 1 else ''}")
                if parts:
                    label += " | " + " + ".join(parts)
                self.count_label.SetLabel(label)

                for i, panel in enumerate(self._pool):
                    if i < len(cards):
                        card = cards[i]
                        if panel.card is card:
                            # Same dict object: the card identity is unchanged, only qty
                            # may have been modified in-place.  Refresh the label only —
                            # no image invalidation or reload needed.
                            panel.update_qty()
                        else:
                            panel.assign_card(card, self.zone)
                            needs_image_load.append(panel)
                        self.grid_sizer.Show(panel, True)
                    else:
                        self.grid_sizer.Show(panel, False)

                self.card_widgets = self._pool[: len(cards)]

                self.grid_sizer.Layout()
                self.scroller.Layout()
                self.scroller.FitInside()
                self.scroller.SetupScrolling(
                    scroll_x=False,
                    scroll_y=True,
                    rate_x=5,
                    rate_y=5,
                    scrollToTop=not preserve_scroll,
                )

                # Switch between the empty-state hint (page 0) and the card
                # grid (page 1) so the workspace always shows something
                # intentional rather than a blank area.
                target_page = 1 if cards else 0
                if self._content_book.GetSelection() != target_page:
                    self._content_book.ChangeSelection(target_page)

                self._restore_selection()
            finally:
                self.scroller.Thaw()
        finally:
            self.Thaw()

        # Fire image loads only for panels whose card assignment changed.
        for panel in needs_image_load:
            panel.load_image_async()

    def _handle_card_click(self, zone: str, card: dict[str, Any], panel: CardBoxPanel) -> None:
        if self.active_panel is panel:
            self.clear_selection()
            return
        if self.active_panel:
            self.active_panel.set_active(False)
            self.active_panel.Update()
        self.active_panel = panel
        self.selected_name = card["name"]
        panel.set_active(True)
        self._notify_selection(card)

    def _restore_selection(self) -> None:
        if not self.selected_name:
            self._notify_selection(None)
            return
        for widget in self.card_widgets:
            if widget.card["name"].lower() == self.selected_name.lower():
                self.active_panel = widget
                widget.set_active(True)
                self._notify_selection(widget.card)
                return
        previously_had_selection = self.selected_name is not None
        self.selected_name = None
        if previously_had_selection:
            self._notify_selection(None)

    def get_selected_card(self) -> dict[str, Any] | None:
        if self.active_panel:
            return self.active_panel.card
        return None

    def focus_card(self, card_name: str) -> bool:
        if not card_name:
            return False
        match = None
        for widget in self.card_widgets:
            if widget.card["name"].lower() == card_name.lower():
                match = widget
                break
        if match is None:
            return False
        if self.active_panel and self.active_panel is not match:
            self.active_panel.set_active(False)
        self.active_panel = match
        self.selected_name = match.card["name"]
        match.set_active(True)
        self.scroller.ScrollChildIntoView(match)
        self._notify_selection(match.card)
        return True

    def clear_selection(self) -> None:
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = None
        self.selected_name = None
        self._notify_selection(None)

    def collapse_active(self) -> None:
        if self.active_panel:
            self.active_panel.set_active(False)
        self.active_panel = None
        self.selected_name = None

    def refresh_card_image(self, card_name: str) -> None:
        if not card_name:
            return
        key = card_name.lower()
        # For DFCs the downloaded name is the combined form "A // B".  Cards in
        # the deck may be stored under the individual face name ("A" or "B"), so
        # build a set of all name variants to match against.
        face_keys: set[str] = {key}
        if "//" in key:
            for part in key.split("//"):
                stripped = part.strip()
                if stripped:
                    face_keys.add(stripped)
        for widget in self.card_widgets:
            if widget.card["name"].lower() in face_keys:
                widget.refresh_image()  # resets state and triggers load_image_async()

    def _notify_selection(self, card: dict[str, Any] | None) -> None:
        if self._on_select:
            self._on_select(self.zone, card)
