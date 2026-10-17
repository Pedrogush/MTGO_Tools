"""Locate the MTGO match window on screen (Windows only).

The opponent tracker already finds the match by window title (any title with
``vs.`` in it, see :mod:`utils.find_opponent_names`); this answers the one
thing that does not: *where* that window is, so the compact chip can start
near the opponent's portrait. Off Windows, or when no match window is open,
every lookup answers ``None``.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from loguru import logger

# A private handle, NOT ``ctypes.windll.user32``: the prototypes below would
# otherwise be assigned on the process-wide instance that ``pygetwindow`` also
# calls through, which is exactly how issue #1013 broke opponent detection
# (see :mod:`automation.server.video_capture`).
_user32 = ctypes.WinDLL("user32") if os.name == "nt" else None

if _user32 is not None:
    _EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [_EnumWindowsProc, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    _user32.GetWindowTextLengthW.restype = ctypes.c_int
    _user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    _user32.GetWindowTextW.restype = ctypes.c_int
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL


def is_match_title(title: str, opponent: str | None = None) -> bool:
    """Whether ``title`` is a match window's, optionally against ``opponent``.

    The same rule the opponent detector applies: the text after the last
    ``vs.`` is the opponent's name.
    """
    if "vs." not in title:
        return False
    found = title.split("vs.")[-1].strip()
    if not found:
        return False
    return opponent is None or found == opponent.strip()


def find_match_window_rect(opponent: str | None = None) -> tuple[int, int, int, int] | None:
    """Screen rectangle ``(x, y, width, height)`` of the visible match window.

    With several matching windows the largest wins: the game window, rather
    than a small chat or popout that happens to carry the same title.
    """
    if _user32 is None:
        return None

    best: list[tuple[int, int, int, int]] = []

    def _visit(hwnd: int, _lparam: int) -> bool:
        try:
            if not _user32.IsWindowVisible(hwnd) or _user32.IsIconic(hwnd):
                return True
            length = _user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return True
            buffer = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buffer, length + 1)
            if not is_match_title(buffer.value, opponent):
                return True
            rect = wintypes.RECT()
            if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return True
            candidate = (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
            if candidate[2] <= 0 or candidate[3] <= 0:
                return True
            if not best or candidate[2] * candidate[3] > best[0][2] * best[0][3]:
                best[:] = [candidate]
        except Exception as exc:  # noqa: BLE001 - one odd window must not end the scan
            logger.debug(f"Skipping window during match-window scan: {exc}")
        return True

    try:
        _user32.EnumWindows(_EnumWindowsProc(_visit), 0)
    except OSError as exc:
        logger.debug(f"Could not enumerate windows for the match window: {exc}")
        return None
    return best[0] if best else None
