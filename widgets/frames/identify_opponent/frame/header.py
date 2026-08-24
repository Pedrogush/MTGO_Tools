"""Top-of-window header construction (deck label, status, action buttons)."""

from __future__ import annotations

import wx

from utils.constants import (
    DARK_BG,
    LIGHT_TEXT,
    OPPONENT_TRACKER_LABEL_MIN_WRAP_WIDTH,
    OPPONENT_TRACKER_SECTION_PADDING,
    SUBDUED_TEXT,
)
from widgets.stylize import apply_type_level, create_divider, stylize_button
from widgets.wx_layout import relayout


class HeaderBuilderMixin:
    """Builds the deck-name label, status line, and the row of header buttons.

    Kept as a mixin (no ``__init__``) so :class:`MTGOpponentDeckSpy` remains the
    single source of truth for instance-state initialization.
    """

    deck_label: wx.StaticText
    status_label: wx.StaticText
    load_arch_btn: wx.Button

    # Unwrapped source text for each header label. ``wx.StaticText.Wrap`` is
    # destructive -- it rewrites the label with hard newlines in it -- so the
    # original string has to be kept to re-wrap at a new width.
    _deck_label_text: str = ""
    _status_label_text: str = ""

    def _header_wrap_width(self) -> int:
        """Wrap width for the header labels: the frame's real usable width.

        The labels used to wrap at a hard-coded 320px whatever the window was
        doing, so a multi-format opponent line broke into a five-line block
        inside a 740px-wide window -- and, because nothing re-ran the layout
        after the label grew, those extra lines painted *over* the panels below
        it. Measuring the window keeps each line on one row until the user
        actually narrows the window, and the re-layout gives the label the
        height it grew to.
        """
        width = self.GetClientSize().GetWidth() - 2 * OPPONENT_TRACKER_SECTION_PADDING
        return max(width, OPPONENT_TRACKER_LABEL_MIN_WRAP_WIDTH)

    def _set_deck_label(self, text: str) -> None:
        """Set the headline label, re-wrapping and re-laying out the header."""
        if text == self._deck_label_text:
            return
        self._deck_label_text = text
        self._apply_header_label(self.deck_label, text)
        self._relayout_header()

    def _set_status_label(self, text: str) -> None:
        """Set the status line, re-wrapping and re-laying out the header."""
        if text == self._status_label_text:
            return
        self._status_label_text = text
        self._apply_header_label(self.status_label, text)
        self._relayout_header()

    def _apply_header_label(self, label: wx.StaticText, text: str) -> None:
        label.SetLabel(text)
        label.Wrap(self._header_wrap_width())

    def _rewrap_header_labels(self) -> None:
        """Re-wrap both header labels to the current window width."""
        self._apply_header_label(self.deck_label, self._deck_label_text)
        self._apply_header_label(self.status_label, self._status_label_text)

    def _relayout_header(self) -> None:
        """Re-run the frame layout so a taller label pushes the panels down.

        Without this the header keeps the height it was given when the frame was
        built and any extra lines overflow on top of the main area.
        """
        panel = getattr(self, "_content_panel", None)
        if panel is not None:
            relayout(panel)

    def _stylize_label(
        self, label: wx.StaticText, *, level: str = "body", subtle: bool = False
    ) -> None:
        label.SetForegroundColour(SUBDUED_TEXT if subtle else LIGHT_TEXT)
        label.SetBackgroundColour(DARK_BG)
        apply_type_level(label, level)

    def _stylize_secondary_button(self, button: wx.Button) -> None:
        stylize_button(button, kind="secondary")

    def _build_header(self, panel: wx.Panel, outer_sizer: wx.Sizer) -> None:
        self._deck_label_text = self._t("tracker.label.not_detected")
        self.deck_label = wx.StaticText(panel, label=self._deck_label_text)
        # The opponent's deck is this window's headline.
        self._stylize_label(self.deck_label, level="heading")
        self.deck_label.Wrap(self._header_wrap_width())
        outer_sizer.Add(self.deck_label, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        self._status_label_text = self._t("tracker.label.watching")
        self.status_label = wx.StaticText(panel, label=self._status_label_text)
        self._stylize_label(self.status_label, level="caption", subtle=True)
        self.status_label.Wrap(self._header_wrap_width())
        outer_sizer.Add(
            self.status_label,
            0,
            wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND,
            OPPONENT_TRACKER_SECTION_PADDING,
        )

        divider = create_divider(panel, vertical=False)
        outer_sizer.Add(
            divider, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING
        )

        controls = wx.BoxSizer(wx.HORIZONTAL)
        outer_sizer.Add(controls, 0, wx.ALL | wx.EXPAND, OPPONENT_TRACKER_SECTION_PADDING)

        controls.AddStretchSpacer(1)

        refresh_button = wx.Button(panel, label=self._t("tracker.btn.refresh"))
        self._stylize_secondary_button(refresh_button)
        refresh_button.Bind(wx.EVT_BUTTON, lambda _evt: self._manual_refresh(force=True))
        controls.Add(refresh_button, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        self.load_arch_btn = wx.Button(panel, label=self._t("tracker.btn.load_archetype"))
        self._stylize_secondary_button(self.load_arch_btn)
        self.load_arch_btn.Bind(wx.EVT_BUTTON, self._on_load_archetype_clicked)
        controls.Add(self.load_arch_btn, 0, wx.RIGHT, OPPONENT_TRACKER_SECTION_PADDING)

        close_button = wx.Button(panel, label=self._t("tracker.btn.close"))
        self._stylize_secondary_button(close_button)
        close_button.Bind(wx.EVT_BUTTON, lambda _evt: self.Close())
        controls.Add(close_button, 0)
