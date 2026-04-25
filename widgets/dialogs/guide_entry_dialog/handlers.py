"""Button handlers for the guide entry dialog."""

from __future__ import annotations

import wx


class GuideEntryDialogHandlersMixin:
    """Button handlers for :class:`GuideEntryDialog`."""

    def _on_save_continue(self, event: wx.Event) -> None:
        # Return wx.ID_APPLY to signal save without closing
        self.EndModal(wx.ID_APPLY)
