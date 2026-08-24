"""The automation capture modules must not set prototypes on a shared DLL handle.

``ctypes.windll`` is a ``LibraryLoader`` that caches one instance per DLL for the
whole process and hands that same object to every importer. So a module that does

    ctypes.windll.user32.GetWindowRect.argtypes = [...]

has not configured *its* ``user32`` -- it has configured everyone's, including
that of any third-party library in the process.

That is not hypothetical here. ``automation/server/video_capture.py`` declared
``GetWindowRect`` as taking ``POINTER(wintypes.RECT)``; ``pygetwindow`` calls the
same function with a ``RECT`` class of its own, so after the import its call
raised ``ArgumentError: expected LP_RECT instance instead of pointer to RECT``.
The raise happened inside an ``EnumWindows`` callback, where ctypes prints
``Exception ignored`` and carries on, so ``getAllTitles()`` returned ``[]``
instead of failing -- and ``utils.find_opponent_names.find_opponent_names()``,
which is the *only* trigger for the opponent tracker's detection, silently
returned nothing for the entire life of any ``--automation`` process (#1013).

The fix is a private ``ctypes.WinDLL(...)`` instance per module. This guard
pins it, because the failure it prevents is invisible: nothing errors, a feature
just stops working.

``tests/ui/test_card_view_viewport_repaint.py`` documents the same trap from the
other side ("``argtypes`` on ``GetDIBits`` first wins -- and ``automation.server``
does"), which is how a second instance of this bug was already being worked
around rather than fixed.
"""

from __future__ import annotations

import ctypes
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.name != "nt",
    reason="ctypes.windll and the Win32 capture modules only exist on Windows.",
)

#: Functions the automation modules declare prototypes for, on the handle they
#: own. Each must be left untouched on the process-wide handle. ``GetWindowRect``
#: is the one that actually broke; the others are on the same shared object and
#: would break some other importer the same way.
_SHARED_USER32_FUNCTIONS = (
    "GetWindowRect",
    "PrintWindow",
    "GetDC",
    "ReleaseDC",
    "SetWindowPos",
    "IsWindowVisible",
)


def _import_capture_modules() -> None:
    """Import both capture modules for their import-time prototype assignments."""
    import automation.server.video_capture  # noqa: F401
    import automation.server.window_capture  # noqa: F401


def test_capture_modules_do_not_touch_shared_user32_prototypes() -> None:
    """Importing the capture modules must leave ``ctypes.windll.user32`` pristine."""
    _import_capture_modules()

    shared = ctypes.windll.user32  # type: ignore[attr-defined]
    polluted = {
        name: getattr(shared, name).argtypes
        for name in _SHARED_USER32_FUNCTIONS
        if getattr(shared, name).argtypes is not None
    }

    assert not polluted, (
        "automation.server set argtypes on the process-wide ctypes.windll.user32. "
        "Use a private ctypes.WinDLL('user32') instead -- the shared handle is "
        f"also pygetwindow's. Polluted: {polluted}"
    )


def test_capture_modules_do_not_touch_shared_gdi32_prototypes() -> None:
    """Same guard for ``gdi32``, which ``video_capture`` also configures."""
    _import_capture_modules()

    shared = ctypes.windll.gdi32  # type: ignore[attr-defined]
    polluted = {
        name: getattr(shared, name).argtypes
        for name in ("BitBlt", "GetDIBits", "CreateCompatibleDC", "SelectObject")
        if getattr(shared, name).argtypes is not None
    }

    assert not polluted, (
        "automation.server set argtypes on the process-wide ctypes.windll.gdi32. "
        f"Use a private ctypes.WinDLL('gdi32') instead. Polluted: {polluted}"
    )


def test_capture_modules_use_private_dll_instances() -> None:
    """The handles the modules hold must not be the cached ``ctypes.windll`` ones.

    The prototype checks above pass trivially if a module simply stops declaring
    prototypes; this one pins the mechanism that makes declaring them safe.
    """
    from automation.server import video_capture, window_capture

    assert video_capture._user32 is not ctypes.windll.user32  # type: ignore[attr-defined]
    assert video_capture._gdi32 is not ctypes.windll.gdi32  # type: ignore[attr-defined]
    assert window_capture._user32 is not ctypes.windll.user32  # type: ignore[attr-defined]


def test_find_opponent_names_survives_importing_the_capture_modules() -> None:
    """The end-to-end shape of #1013: detection must still be callable afterwards.

    It cannot assert on *which* windows exist -- that depends on the machine --
    but it can assert the call completes and returns a list. Before the fix this
    returned ``[]`` on every machine and every input, because each per-window
    ``GetWindowRect`` raised inside ``pygetwindow``'s enumeration callback.
    """
    from utils.find_opponent_names import find_opponent_names

    _import_capture_modules()

    assert isinstance(find_opponent_names(), list)
