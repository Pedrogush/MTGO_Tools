"""Public accessors for the feedback dialog."""

from __future__ import annotations

from widgets.checkbox import DarkCheckBox


class FeedbackDialogPropertiesMixin:
    """Public state accessors for :class:`FeedbackDialog`."""

    _event_log_check: DarkCheckBox

    @property
    def event_logging_enabled(self) -> bool:
        return self._event_log_check.GetValue()
