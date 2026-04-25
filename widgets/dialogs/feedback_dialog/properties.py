"""Public accessors for the feedback dialog."""

from __future__ import annotations

import wx


class FeedbackDialogPropertiesMixin:
    """Public state accessors for :class:`FeedbackDialog`."""

    _event_log_check: wx.CheckBox

    @property
    def event_logging_enabled(self) -> bool:
        return self._event_log_check.GetValue()
