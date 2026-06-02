"""Stateless session-restore decision helpers for the app-frame handlers.

Pure functions with no ``self`` and no ``wx`` dependency, factored out of the
:meth:`AppFrameHandlersMixin._restore_session_state` handler so the gate logic
can be exercised without a ``wx.App`` (Humble Object pattern).
"""

from __future__ import annotations


def should_show_tutorial(*, tutorial_shown: bool, automation_enabled: bool) -> bool:
    """Return whether the first-run tutorial should be scheduled on startup.

    The tutorial is shown only when the user has never seen it and the app is
    not being driven by automation (where interactive dialogs would block).
    """
    return not tutorial_shown and not automation_enabled
