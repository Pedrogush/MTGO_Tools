"""Coordinates session state restoration with UI."""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from widgets.app_frame import AppFrame


class SessionUICoordinator:
    """Coordinates restoring session state into UI components."""

    def __init__(self, frame: "AppFrame"):
        self.frame = frame

    def restore_session_state(self) -> None:
        """Restore complete session state into UI."""
        state = self.frame.controller.session_manager.restore_session_state(
            self.frame.controller.zone_cards
        )

        # Restore left panel mode
        self.frame._show_left_panel(state.get("left_mode", "research"), force=True)

        has_saved_deck = bool(state.get("zone_cards"))

        # Restore zone cards
        if has_saved_deck:
            if self.frame.controller.card_repo.is_card_data_ready():
                self.frame._render_current_deck()
            else:
                self.frame._pending_deck_restore = True
                self.frame._set_status("Loading card database to restore saved deck...")
                self.frame.ensure_card_data_loaded()

        # Restore deck text
        if (
            state.get("deck_text")
            and self.frame.controller.card_repo.is_card_data_ready()
            and not has_saved_deck
        ):
            self.frame._update_stats(state["deck_text"])
            self.frame.copy_button.Enable(True)
            self.frame.save_button.Enable(True)
