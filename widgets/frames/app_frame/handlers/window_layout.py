"""Window persistence, sizing, and collapsible-panel layout for :class:`AppFrame`."""

from __future__ import annotations

from typing import TYPE_CHECKING

import wx
from loguru import logger

from utils.constants import APP_FRAME_MIN_SIZE, APP_FRAME_SIZE
from widgets.wx_layout import set_shown

if TYPE_CHECKING:
    from widgets.frames.app_frame.protocol import AppFrameProto

    _Base = AppFrameProto
else:
    _Base = object


class WindowLayoutHandlers(_Base):
    """Window persistence, display-aware sizing, and side-panel collapse toggles.

    Kept as a mixin (no ``__init__``) so :class:`AppFrame` remains the single
    source of truth for instance-state initialization.
    """

    def _save_window_settings(self) -> None:
        pos = self.GetPosition()
        size = self.GetSize()
        self.controller.save_settings(
            window_size=(size.width, size.height), screen_pos=(pos.x, pos.y)
        )

    def _apply_window_preferences(self) -> None:
        state = self.controller.session_manager.restore_session_state(self.controller.zone_cards)

        # Restore the collapsed/expanded state of the side panels before sizing,
        # so the recomputed minimum reflects what is actually shown.
        if state.get("left_collapsed"):
            self._set_left_collapsed(True, persist=False)
        if state.get("inspector_collapsed"):
            self._set_inspector_collapsed(True, persist=False)

        area = self._target_display_client_area()

        # On a display too small to host the preferred size, maximize to use the
        # full usable area. Also collapse the (tall) inspector by default the
        # first time we hit such a screen, so the layout fits without the card
        # image forcing the window taller than the display (the user can expand
        # it again — its toggle persists from then on).
        too_small = APP_FRAME_SIZE[0] > area.width or APP_FRAME_SIZE[1] > area.height
        if too_small:
            if "inspector_collapsed" not in state:
                self._set_inspector_collapsed(True, persist=False)
            self.Maximize(True)
            return

        size = state.get("window_size") or APP_FRAME_SIZE
        try:
            width = min(int(size[0]), area.width)
            height = min(int(size[1]), area.height)
        except (TypeError, ValueError):
            logger.debug("Ignoring invalid saved window size")
            width, height = APP_FRAME_SIZE
        self.SetSize(wx.Size(width, height))

        pos = state.get("screen_pos")
        if pos:
            try:
                x = max(area.x, min(int(pos[0]), area.x + area.width - width))
                y = max(area.y, min(int(pos[1]), area.y + area.height - height))
                self.SetPosition(wx.Point(x, y))
            except (TypeError, ValueError):
                logger.debug("Ignoring invalid saved window position")
                self.Centre(wx.BOTH)
        else:
            self.Centre(wx.BOTH)

    def _target_display_client_area(self) -> wx.Rect:
        """Usable area (excluding the taskbar) of the display hosting the frame."""
        index = wx.Display.GetFromWindow(self)
        if index == wx.NOT_FOUND:
            index = 0
        try:
            return wx.Display(index).GetClientArea()
        except (RuntimeError, AssertionError):
            return wx.Display(0).GetClientArea()

    def _apply_min_size(self) -> None:
        """Set the frame's minimum size to the larger of the hard floor and the
        current content minimum.

        Recomputed whenever a side panel is collapsed/expanded so that, e.g.,
        collapsing the tall inspector lets the window shrink below the inspector's
        natural height, while expanding it raises the floor again.
        """
        if not self.root_panel or not self.root_panel.GetSizer():
            self.SetMinSize(APP_FRAME_MIN_SIZE)
            return
        self.root_panel.Layout()
        min_size = self.root_panel.GetSizer().GetMinSize()
        try:
            min_size = self.ClientToWindowSize(min_size)
        except AttributeError:
            pass
        self.SetMinSize(
            wx.Size(
                max(APP_FRAME_MIN_SIZE[0], min_size.GetWidth()),
                max(APP_FRAME_MIN_SIZE[1], min_size.GetHeight()),
            )
        )

    # ------------------------------------------------------------------ Collapsible side panels ---------------------------------------------
    def toggle_left_panel(self) -> None:
        self._set_left_collapsed(not self._left_collapsed)

    def toggle_inspector(self) -> None:
        self._set_inspector_collapsed(not self._inspector_collapsed)

    def _set_left_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        self._left_collapsed = collapsed
        if self.left_toggle_btn:
            # ▶ invites expanding (panel hidden to the left); ◀ invites collapsing.
            self.left_toggle_btn.SetLabel("▶" if collapsed else "◀")
        self._relayout_after_toggle(self.left_panel_window, not collapsed)
        if persist:
            self.controller.save_settings(left_collapsed=collapsed)

    def _set_inspector_collapsed(self, collapsed: bool, *, persist: bool = True) -> None:
        self._inspector_collapsed = collapsed
        if self.inspector_toggle_btn:
            # ◀ invites expanding (panel hidden to the right); ▶ invites collapsing.
            self.inspector_toggle_btn.SetLabel("◀" if collapsed else "▶")
        self._relayout_after_toggle(self.inspector_panel, not collapsed)
        if persist:
            self.controller.save_settings(inspector_collapsed=collapsed)

    def _relayout_after_toggle(self, panel: wx.Window | None, shown: bool) -> None:
        if self.root_panel:
            # set_shown repaints the whole frame so the toggled panel never
            # leaves ghost pixels over the toolbar (see widgets.wx_layout).
            set_shown(panel, shown, relayout_from=self.root_panel)
        self._apply_min_size()
