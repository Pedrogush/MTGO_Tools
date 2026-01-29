"""Builder for main application toolbar."""

from collections.abc import Callable
from typing import TYPE_CHECKING

import wx

from widgets.buttons.toolbar_buttons import ToolbarButtons

if TYPE_CHECKING:
    pass


class ToolbarBuilder:
    """Builds the main application toolbar with callbacks."""

    def __init__(
        self,
        on_open_opponent_tracker: Callable[[], None],
        on_open_timer_alert: Callable[[], None],
        on_open_match_history: Callable[[], None],
        on_open_metagame_analysis: Callable[[], None],
        on_load_collection: Callable[[], None],
        on_download_card_images: Callable[[], None],
        on_update_card_database: Callable[[], None],
    ):
        self.on_open_opponent_tracker = on_open_opponent_tracker
        self.on_open_timer_alert = on_open_timer_alert
        self.on_open_match_history = on_open_match_history
        self.on_open_metagame_analysis = on_open_metagame_analysis
        self.on_load_collection = on_load_collection
        self.on_download_card_images = on_download_card_images
        self.on_update_card_database = on_update_card_database

    def build(self, parent: wx.Window) -> ToolbarButtons:
        """Build and return the toolbar."""
        return ToolbarButtons(
            parent,
            on_open_opponent_tracker=self.on_open_opponent_tracker,
            on_open_timer_alert=self.on_open_timer_alert,
            on_open_match_history=self.on_open_match_history,
            on_open_metagame_analysis=self.on_open_metagame_analysis,
            on_load_collection=self.on_load_collection,
            on_download_card_images=self.on_download_card_images,
            on_update_card_database=self.on_update_card_database,
        )
