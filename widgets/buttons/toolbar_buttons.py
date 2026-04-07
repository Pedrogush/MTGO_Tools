"""
Toolbar Buttons - Shared utility buttons for the deck selector toolbar.

Provides quick-access buttons for opponent tracking, timers, history, and settings.
"""

from collections.abc import Callable

import wx

from utils.stylize import stylize_button


class ToolbarButtons(wx.Panel):
    """Panel containing the deck selector toolbar buttons."""

    def __init__(
        self,
        parent: wx.Window,
        on_open_opponent_tracker: Callable[[], None] | None = None,
        on_open_timer_alert: Callable[[], None] | None = None,
        on_open_match_history: Callable[[], None] | None = None,
        on_open_metagame_analysis: Callable[[], None] | None = None,
        on_open_top_cards: Callable[[], None] | None = None,
        on_open_settings_menu: Callable[[wx.Window], None] | None = None,
        labels: dict[str, str] | None = None,
    ):
        super().__init__(parent)
        labels = labels or {}

        self._button_row = wx.BoxSizer(wx.HORIZONTAL)
        self.SetSizer(self._button_row)

        # Navigation group — primary actions
        self.opponent_tracker_button = self._add_button(
            labels.get("opponent_tracker", "Opponent Tracker"),
            on_open_opponent_tracker,
            tooltip=labels.get("opponent_tracker_tooltip", ""),
        )
        self.timer_alert_button = self._add_button(
            labels.get("timer_alert", "Timer Alert"),
            on_open_timer_alert,
            tooltip=labels.get("timer_alert_tooltip", ""),
        )
        self.match_history_button = self._add_button(
            labels.get("match_history", "Match History"),
            on_open_match_history,
            tooltip=labels.get("match_history_tooltip", ""),
        )
        self.metagame_analysis_button = self._add_button(
            labels.get("metagame_analysis", "Metagame Analysis"),
            on_open_metagame_analysis,
            tooltip=labels.get("metagame_analysis_tooltip", ""),
        )
        self.top_cards_button = self._add_button(
            labels.get("top_cards", "Top Cards"),
            on_open_top_cards,
            tooltip=labels.get("top_cards_tooltip", ""),
        )

        self._button_row.AddStretchSpacer(1)
        self._add_divider(gap=10)
        self.settings_button = wx.Button(self, label=labels.get("settings", "\u2699"))
        stylize_button(self.settings_button)
        self.settings_button.SetToolTip(labels.get("settings_tooltip", "Settings"))
        if on_open_settings_menu:
            self.settings_button.Bind(
                wx.EVT_BUTTON,
                lambda _evt, btn=self.settings_button, cb=on_open_settings_menu: cb(btn),
            )
        else:  # pragma: no cover - defensive fallback
            self.settings_button.Disable()
        self._button_row.Add(self.settings_button, 0)

    # ============= Helpers =============

    def _add_button(
        self,
        label: str,
        handler: Callable[[], None] | None,
        *,
        margin: int = 6,
        tooltip: str = "",
    ) -> wx.Button:
        """Create a toolbar button and bind its handler if provided."""
        button = wx.Button(self, label=label)
        stylize_button(button)
        if tooltip:
            button.SetToolTip(tooltip)
        if handler:
            button.Bind(wx.EVT_BUTTON, lambda _evt, cb=handler: cb())
        else:  # pragma: no cover - defensive fallback
            button.Disable()
        self._button_row.Add(button, 0, wx.RIGHT, margin)
        return button

    def _add_divider(self, gap: int = 8) -> None:
        """Add a vertical line divider between button groups."""
        self._button_row.AddSpacer(gap)
        line = wx.StaticLine(self, style=wx.LI_VERTICAL)
        self._button_row.Add(line, 0, wx.EXPAND | wx.TOP | wx.BOTTOM, 4)
        self._button_row.AddSpacer(gap)


__all__ = ["ToolbarButtons"]
