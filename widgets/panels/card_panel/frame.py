"""UI construction for :class:`CardPanel` — a two-tab notebook (Oracle / Stats).

Replaces the standalone oracle text panel that previously sat in the bottom
right of the app. Tab 1 renders the card as MTG-card-like HTML so the textual
data stays readable even when the selected printing has no oracle text on the
art (full-art promos, foreign-language printings).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import wx
import wx.html

from utils.constants import (
    CARD_ORACLE_MIN_HEIGHT,
    DARK_PANEL,
    LIGHT_TEXT,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SUBDUED_TEXT,
)
from widgets.mana_icon_factory import ManaIconFactory
from widgets.notebook import make_flat_notebook
from widgets.panels.card_panel.handlers import CardPanelHandlersMixin
from widgets.panels.card_panel.properties import CardPanelPropertiesMixin
from widgets.panels.card_panel.rule_popup import RulePopupFrame
from widgets.stylize import apply_type_level, stylize_scrollable


def _default_t(key: str, **fmt: Any) -> str:
    return key.format(**fmt) if fmt else key


class CardPanel(
    CardPanelHandlersMixin,
    CardPanelPropertiesMixin,
    wx.Panel,
):
    """Two-tab notebook displaying card information and play stats."""

    def __init__(
        self,
        parent: wx.Window,
        controller: Any,
        mana_icons: ManaIconFactory | None = None,
        t: Callable[..., str] | None = None,
        keyword_lookup_source: Callable[[], Mapping[str, Any]] | None = None,
    ):
        super().__init__(parent)
        self.SetBackgroundColour(DARK_PANEL)
        self.controller = controller
        self.mana_icons = mana_icons or ManaIconFactory()
        self._t = t or _default_t

        def _default_keyword_lookup_source() -> Mapping[str, Any]:
            try:
                return controller.comp_rules_service.get_keyword_lookup()
            except Exception:
                return {}

        self._keyword_lookup_source = keyword_lookup_source or _default_keyword_lookup_source
        self._rule_popup: RulePopupFrame | None = None

        self._current_meta: Any = None
        self._current_printing: dict[str, Any] | None = None
        self._current_format: str | None = None
        self._current_archetype: dict[str, Any] | None = None
        self._current_radar: Any | None = None

        self._build_ui()
        self.clear()

    def _build_ui(self) -> None:
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)

        # FlatNotebook, not wx.Notebook: the native MSW tab control ignores both
        # SetBackgroundColour and SetForegroundColour, so this rendered a white tab
        # strip with black text about 400px from the deck workspace's dark
        # FlatNotebook (issue #962, C3). Migration is the only fix there is.
        self.notebook = make_flat_notebook(self)
        sizer.Add(self.notebook, 1, wx.EXPAND | wx.ALL, SPACE_SM)

        self._build_oracle_tab()
        self._build_stats_tab()

    def _build_oracle_tab(self) -> None:
        oracle_panel = wx.Panel(self.notebook)
        oracle_panel.SetBackgroundColour(DARK_PANEL)
        sizer = wx.BoxSizer(wx.VERTICAL)
        oracle_panel.SetSizer(sizer)

        self.oracle_html = wx.html.HtmlWindow(
            oracle_panel,
            style=wx.html.HW_SCROLLBAR_AUTO | wx.NO_BORDER,
        )
        stylize_scrollable(self.oracle_html, surface="panel")
        self.oracle_html.SetBorders(2)
        self.oracle_html.SetMinSize((-1, CARD_ORACLE_MIN_HEIGHT))
        self.oracle_html.Bind(wx.html.EVT_HTML_LINK_CLICKED, self._on_oracle_link_clicked)
        sizer.Add(self.oracle_html, 1, wx.EXPAND | wx.ALL, SPACE_SM)

        self.notebook.AddPage(oracle_panel, self._t("card_panel.tab.oracle_text"))

    def _build_stats_tab(self) -> None:
        stats_panel = wx.ScrolledWindow(self.notebook, style=wx.VSCROLL)
        stylize_scrollable(stats_panel, surface="panel")
        stats_panel.SetScrollRate(0, 10)
        sizer = wx.BoxSizer(wx.VERTICAL)
        stats_panel.SetSizer(sizer)
        self.stats_panel = stats_panel
        # Three of this tab's labels carry variable-length content -- the card
        # name, the format header and the archetype header -- and a plain
        # wx.StaticText reports its whole single line as its best width. That
        # width propagates up through the notebook to the whole inspector
        # column, which is what made the app's both-panels-expanded minimum
        # depend on *which card was loaded* (phase 3b measured 267 vs 350, i.e.
        # a 1393 vs 1433 window floor). They are re-wrapped to the panel instead;
        # see _rewrap_flowing_labels.
        self._flowing_label_text: dict[int, str] = {}
        stats_panel.Bind(wx.EVT_SIZE, self._on_stats_panel_resize)
        self.Bind(wx.EVT_SIZE, self._on_panel_resize)

        # S2. The four levels of this list used to be indented 4 / 6 / 12 px --
        # a 4->6 step is 2px and is simply not seen, so the hierarchy was
        # carried by nothing. Levels now step 8 / 8 / 16 / 24 on the 4px grid
        # and are backed by type and tone rather than indent alone:
        #   L1 card name          heading, primary
        #   L2 format / archetype body,    primary
        #   L3 mainboard/sideboard body,    secondary
        #   L4 the numbers        caption, secondary
        self.stats_card_label = wx.StaticText(stats_panel, label="")
        apply_type_level(self.stats_card_label, "heading")
        self.stats_card_label.SetForegroundColour(LIGHT_TEXT)
        sizer.Add(self.stats_card_label, 0, wx.ALL, SPACE_SM)

        self.stats_format_header = self._make_subheader(stats_panel)
        sizer.Add(self.stats_format_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)
        self.stats_format_total = self._make_value_label(stats_panel)
        sizer.Add(self.stats_format_total, 0, wx.LEFT | wx.RIGHT, SPACE_MD)
        self.stats_format_avg = self._make_value_label(stats_panel)
        sizer.Add(self.stats_format_avg, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, SPACE_MD)

        self.stats_archetype_header = self._make_subheader(stats_panel)
        sizer.Add(self.stats_archetype_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_SM)

        self.stats_main_header = wx.StaticText(
            stats_panel, label=self._t("card_panel.stats.mainboard")
        )
        apply_type_level(self.stats_main_header, "body")
        self.stats_main_header.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.stats_main_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_MD)
        self.stats_main_total = self._make_value_label(stats_panel)
        self.stats_main_avg = self._make_value_label(stats_panel)
        self.stats_main_karsten = self._make_value_label(stats_panel)
        self.stats_main_inclusion = self._make_value_label(stats_panel)
        for w in (
            self.stats_main_total,
            self.stats_main_avg,
            self.stats_main_karsten,
            self.stats_main_inclusion,
        ):
            sizer.Add(w, 0, wx.LEFT | wx.RIGHT, SPACE_LG)

        self.stats_side_header = wx.StaticText(
            stats_panel, label=self._t("card_panel.stats.sideboard")
        )
        apply_type_level(self.stats_side_header, "body")
        self.stats_side_header.SetForegroundColour(SUBDUED_TEXT)
        sizer.Add(self.stats_side_header, 0, wx.LEFT | wx.RIGHT | wx.TOP, SPACE_MD)
        self.stats_side_total = self._make_value_label(stats_panel)
        self.stats_side_avg = self._make_value_label(stats_panel)
        self.stats_side_karsten = self._make_value_label(stats_panel)
        self.stats_side_inclusion = self._make_value_label(stats_panel)
        for w in (
            self.stats_side_total,
            self.stats_side_avg,
            self.stats_side_karsten,
            self.stats_side_inclusion,
        ):
            sizer.Add(w, 0, wx.LEFT | wx.RIGHT, SPACE_LG)

        self.notebook.AddPage(stats_panel, self._t("card_panel.tab.stats"))

    # ------------------------------------------------------------------
    # Flowing (re-wrapped) stats labels
    # ------------------------------------------------------------------

    def set_flowing_label(self, label: wx.StaticText, text: str) -> None:
        """Set a variable-length Stats label, remembering its unwrapped text.

        ``wx.StaticText.Wrap`` rewrites the label in place, so the original
        string has to be kept somewhere or the second wrap re-wraps the first
        wrap's output. Keyed by id() rather than by attribute name so a caller
        only has to hold the widget.
        """
        self._flowing_label_text[id(label)] = text
        label.SetLabel(text)
        self._wrap_one(label)

    def _wrap_width(self) -> int:
        # SPACE_LG is the deepest indent any of these labels sits at; taking the
        # deepest one for all three keeps the right margin ragged-free without
        # measuring each label's own border.
        #
        # The fallbacks matter. A notebook page that has never been selected is
        # never sized -- wx leaves it at 20x20 -- so reading the Stats page's own
        # client width returns a negative wrap width and the labels are set at
        # their full single-line length. That is not a cosmetic miss: those
        # lengths are what the notebook reports as its best width, so an unwrapped
        # hidden page sets the whole inspector column's minimum. Measured in
        # pt-BR, where "Selecione uma carta para ver estatisticas." is 313px in a
        # 300px column. Each fallback is the same measure one level out.
        # The **widest** of the three, not the first plausible one: an unshown
        # page is not reliably 20x20, it is whatever the last layout left, and
        # it was measured at a 3px client width here. A page can never
        # legitimately be wider than the notebook that holds it or the panel
        # that holds that, so taking the max cannot over-wrap and does not need
        # a magic "is this width real yet" threshold.
        width = max(
            self.stats_panel.GetClientSize().GetWidth(),
            self.notebook.GetClientSize().GetWidth(),
            self.GetClientSize().GetWidth(),
        )
        return width - (SPACE_LG * 2)

    def _wrap_one(self, label: wx.StaticText) -> None:
        width = self._wrap_width()
        if width <= 0:
            return
        text = self._flowing_label_text.get(id(label))
        if text is None:
            return
        label.SetLabel(text)
        label.Wrap(width)

    def _rewrap_flowing_labels(self) -> None:
        for label in (
            self.stats_card_label,
            self.stats_format_header,
            self.stats_archetype_header,
        ):
            self._wrap_one(label)

    def _on_stats_panel_resize(self, event: wx.SizeEvent) -> None:
        event.Skip()
        self._rewrap_flowing_labels()
        self.stats_panel.Layout()

    def _on_panel_resize(self, event: wx.SizeEvent) -> None:
        # The Stats page only gets EVT_SIZE once it has been selected, so the
        # panel's own resize is what keeps a never-shown page's labels wrapped
        # to the column they will appear in.
        event.Skip()
        self._rewrap_flowing_labels()

    def _make_subheader(self, parent: wx.Window) -> wx.StaticText:
        """L2 of the Stats hierarchy: primary tone, body weight, no bold.

        These were bold. So was the card name above them and so was every other
        label in the app, which is exactly why bold marked nothing.
        """
        label = wx.StaticText(parent, label="")
        apply_type_level(label, "body")
        label.SetForegroundColour(LIGHT_TEXT)
        return label

    def _make_value_label(self, parent: wx.Window) -> wx.StaticText:
        """L4 of the Stats hierarchy: the numbers themselves."""
        label = wx.StaticText(parent, label="")
        apply_type_level(label, "caption")
        label.SetForegroundColour(SUBDUED_TEXT)
        return label
