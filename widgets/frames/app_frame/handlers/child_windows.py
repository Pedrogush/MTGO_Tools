"""Child-window handlers: tracker/timer/history/metagame/top-cards/radar, feedback, close."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.constants import LOGS_DIR
from widgets.dialogs.feedback_dialog import show_feedback_dialog
from widgets.frames.app_frame.handlers.ui_helpers import open_child_window, widget_exists
from widgets.frames.identify_opponent import MTGOpponentDeckSpy
from widgets.frames.match_history import MatchHistoryFrame
from widgets.frames.radar import RadarFrame
from widgets.frames.timer_alert import TimerAlertFrame
from widgets.frames.top_cards import TopCardsFrame

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class ChildWindowHandlers(_Base):
    """Open/close auxiliary frames, feedback dialog, and main-window close."""

    def open_opponent_tracker(self: AppFrame) -> None:
        existing = getattr(self, "tracker_window", None)
        if widget_exists(existing):
            existing.Raise()
            return

        def on_tracker_close(evt: wx.CloseEvent, attr: str) -> None:
            self._handle_child_close(evt, attr)
            self.Show()
            self.Raise()

        window = open_child_window(
            self,
            "tracker_window",
            MTGOpponentDeckSpy,
            "Opponent Tracker",
            on_tracker_close,
            controller=self.controller,
            locale=self.locale,
        )
        if window is not None:
            self.Hide()

    def open_timer_alert(self: AppFrame) -> None:
        open_child_window(
            self,
            "timer_window",
            TimerAlertFrame,
            "Timer Alert",
            self._handle_child_close,
            controller=self.controller,
            locale=self.locale,
        )

    def open_match_history(self: AppFrame) -> None:
        open_child_window(
            self,
            "history_window",
            MatchHistoryFrame,
            "Match History",
            self._handle_child_close,
            controller=self.controller,
            locale=self.locale,
        )

    def open_metagame_analysis(self: AppFrame) -> None:
        # Imported lazily: pulling in MetagameAnalysisFrame eagerly drags
        # matplotlib (a heavy cold-import) onto the startup path. It is only
        # needed when the user deliberately opens this chart.
        from widgets.frames.metagame_analysis import MetagameAnalysisFrame

        open_child_window(
            self,
            "metagame_window",
            MetagameAnalysisFrame,
            "Metagame Analysis",
            self._handle_child_close,
            controller=self.controller,
            locale=self.locale,
        )

    def open_top_cards(self: AppFrame) -> None:
        open_child_window(
            self,
            "top_cards_window",
            TopCardsFrame,
            "Top Cards",
            self._handle_child_close,
            controller=self.controller,
            locale=self.locale,
        )

    def open_radar(self: AppFrame, archetype_name: str | None = None) -> RadarFrame | None:
        window = open_child_window(
            self,
            "radar_window",
            RadarFrame,
            "Radar",
            self._handle_child_close,
            controller=self.controller,
            metagame_repo=self.controller.metagame_repo,
            format_name=self.current_format,
            on_use_for_search=self._on_radar_use_for_search,
            locale=self.locale,
        )
        if window and archetype_name:
            window.generate_for_archetype(archetype_name)
        return window

    def _open_feedback_dialog(self: AppFrame) -> None:
        show_feedback_dialog(
            self,
            LOGS_DIR,
            event_logging_enabled=self.controller.get_event_logging_enabled(),
            on_event_logging_changed=self.controller.set_event_logging_enabled,
        )

    def _handle_child_close(self: AppFrame, event: wx.CloseEvent, attr: str) -> None:
        setattr(self, attr, None)
        event.Skip()

    def on_window_change(self: AppFrame, event: wx.Event) -> None:
        self._schedule_settings_save()
        event.Skip()

    def on_close(self: AppFrame, event: wx.CloseEvent) -> None:
        if self._save_timer and self._save_timer.IsRunning():
            self._save_timer.Stop()
        if self._filter_debounce_timer and self._filter_debounce_timer.IsRunning():
            self._filter_debounce_timer.Stop()
        self._save_window_settings()
        for attr in (
            "tracker_window",
            "timer_window",
            "history_window",
            "metagame_window",
            "top_cards_window",
            "radar_window",
        ):
            window = getattr(self, attr)
            if widget_exists(window):
                window.Destroy()
                setattr(self, attr, None)
        if self.mana_keyboard_window and self.mana_keyboard_window.IsShown():
            self.mana_keyboard_window.Destroy()
            self.mana_keyboard_window = None
        self.controller.shutdown()
        event.Skip()
