"""Window placement and appearance preferences for the opponent tracker.

Positions the overlay beside its parent (falling back across displays) and
restores any saved position / dark-theme sizing on show.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants import (
    APP_FRAME_SIZE,
    DARK_BG,
    OPPONENT_TRACKER_DEFAULT_X_GAP,
    OPPONENT_TRACKER_FRAME_SIZE,
    OPPONENT_TRACKER_MIN_SIZE,
)

if TYPE_CHECKING:
    from widgets.frames.identify_opponent.protocol import MTGOpponentDeckSpyProto

    _Base = MTGOpponentDeckSpyProto
else:
    _Base = object


class WindowPlacementMixin(_Base):
    """Overlay positioning and appearance preferences."""

    def _place_beside_parent(self) -> None:
        parent = self.GetParent()
        if parent is None:
            return
        try:
            pr = parent.GetRect()
            my_size = self.GetSize()
            display_idx = wx.Display.GetFromWindow(parent)
            if display_idx == wx.NOT_FOUND:
                display_idx = 0
            client_area = wx.Display(display_idx).GetClientArea()
            x = pr.GetRight() + OPPONENT_TRACKER_DEFAULT_X_GAP
            y = pr.GetTop()
            # If it doesn't fit to the right, try the left side of the parent
            if x + my_size.width > client_area.GetRight():
                x = pr.GetLeft() - my_size.width - OPPONENT_TRACKER_DEFAULT_X_GAP
            # Clamp to client area
            x = max(client_area.GetLeft(), min(x, client_area.GetRight() - my_size.width))
            y = max(client_area.GetTop(), min(y, client_area.GetBottom() - my_size.height))
            self.SetPosition(wx.Point(x, y))
        except (RuntimeError, AttributeError):
            logger.debug("Could not compute default tracker position from parent")

    def _apply_window_preferences(self) -> None:
        self.SetBackgroundColour(DARK_BG)
        self.SetMinSize(wx.Size(*OPPONENT_TRACKER_MIN_SIZE))

        # Match the main app's height so the tracker feels aligned when placed side by side.
        try:
            display_idx = wx.Display.GetFromWindow(self) if self.IsShown() else 0
            if display_idx == wx.NOT_FOUND:
                display_idx = 0
            client_area = wx.Display(display_idx).GetClientArea()
            frame_w, _ = OPPONENT_TRACKER_FRAME_SIZE
            parent = self.GetParent()
            main_h = parent.GetSize().GetHeight() if parent is not None else APP_FRAME_SIZE[1]
            self.SetSize(frame_w, min(main_h, client_area.GetHeight()))
        except Exception:
            pass  # fall back to the constant size set in __init__

        if getattr(self, "_saved_position", None):
            try:
                x, y = self._saved_position
                self.SetPosition(wx.Point(int(x), int(y)))
            except (TypeError, ValueError, RuntimeError):
                logger.debug("Ignoring invalid saved window position")
                self._place_beside_parent()
        else:
            self._place_beside_parent()
