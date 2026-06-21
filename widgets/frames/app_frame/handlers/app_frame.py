"""Session restore, auxiliary window openers, and debounce-timer helpers for the main application frame."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx

from utils.runtime_flags import is_automation_enabled
from widgets.dialogs.help_dialog import show_help
from widgets.dialogs.tutorial_dialog import show_tutorial
from widgets.frames.app_frame.handlers.session_logic import should_show_tutorial
from widgets.frames.mana_keyboard import open_mana_keyboard

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class AppFrameHandlersMixin(_Base):
    """Session restore, auxiliary openers, and debounce-timer handlers for :class:`AppFrame`.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    # ------------------------------------------------------------------ Left panel helpers -------------------------------------------------
    def _show_left_panel(self, mode: str, force: bool = False) -> None:
        target = "builder" if mode == "builder" else "research"
        if self.left_stack:
            index = 1 if target == "builder" else 0
            if force or self.left_stack.GetSelection() != index:
                self.left_stack.ChangeSelection(index)
        if target == "builder":
            self.ensure_card_data_loaded()
        if force or self.left_mode != target:
            self.left_mode = target
            self._schedule_settings_save()

    def _open_full_mana_keyboard(self) -> None:
        self.mana_keyboard_window = open_mana_keyboard(
            self, self.mana_icons, self.mana_keyboard_window, self._on_mana_keyboard_closed
        )

    def _open_tutorial(self) -> None:
        show_tutorial(self, locale=self.locale)
        self.controller.session_manager.mark_tutorial_shown()

    def _open_help(self, topic: str | None = None) -> None:
        show_help(self, topic=topic)

    def _open_rules_browser(self) -> None:
        # Lazily imported so launching the rest of the app stays cheap when
        # the user never opens the browser.
        from widgets.frames.app_frame.handlers.ui_helpers import open_child_window
        from widgets.frames.rules_browser import RulesBrowserFrame

        open_child_window(
            self,
            "_rules_browser_window",
            RulesBrowserFrame,
            "Comprehensive Rules",
            self._handle_child_close,
            controller=self.controller,
            locale=self.locale,
        )

    def _restore_session_state(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)
        if should_show_tutorial(
            tutorial_shown=self.controller.session_manager.is_tutorial_shown(),
            automation_enabled=is_automation_enabled(),
        ):
            wx.CallAfter(self._open_tutorial)

        # Restore left panel mode
        self._show_left_panel(state["left_mode"], force=True)

        has_saved_deck = bool(state.get("zone_cards"))

        # Restore zone cards
        if has_saved_deck:
            if self.controller.card_repo.is_card_data_ready():
                self._render_current_deck()
            else:
                self._pending_deck_restore = True
                self._set_status("app.status.restoring_deck")
                self.ensure_card_data_loaded()

        # Restore deck text
        if (
            state.get("deck_text")
            and self.controller.card_repo.is_card_data_ready()
            and not has_saved_deck
        ):
            self._update_stats(state["deck_text"])
            self.copy_button.Enable(True)
            self.save_button.Enable(True)
            self.deck_notes_panel.load_notes_for_current()
            self._load_guide_for_current()

    def _schedule_settings_save(self) -> None:
        if self._save_timer is None:
            self._save_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_pending_settings, self._save_timer)
        if self._save_timer.IsRunning():
            self._save_timer.Stop()
        self._save_timer.StartOnce(600)

    def _flush_pending_settings(self, _event: wx.TimerEvent) -> None:
        self._save_window_settings()

    def _schedule_filter_debounce(self) -> None:
        if self._filter_debounce_timer is None:
            self._filter_debounce_timer = wx.Timer(self)
            self.Bind(wx.EVT_TIMER, self._flush_deck_filters, self._filter_debounce_timer)
        if self._filter_debounce_timer.IsRunning():
            self._filter_debounce_timer.Stop()
        self._filter_debounce_timer.StartOnce(250)

    def _flush_deck_filters(self, _event: wx.TimerEvent) -> None:
        self._apply_deck_filters()
