"""Pure-Win32 GDI frame grabber plus a background-thread video recorder.

Why this exists separately from ``screenshot.py``
-------------------------------------------------
``screenshot.py`` captures through ``wx.Bitmap`` / ``wx.MemoryDC``, which must
only be touched on the wx main thread.  Every automation command is also
dispatched onto the main thread (``transport.TransportMixin._execute_command``
wraps the handler in ``wx.CallAfter``).  That makes the existing screenshot
path useless for capturing a *transient* frame painted **during** a main-thread
layout toggle: by the time a second main-thread command runs, the toggle
handler has already returned and the window is back at rest.

To catch a frame mid-transition the grabber has to run on a *different* thread,
concurrently with the main thread that is executing the toggle.  Everything in
this module therefore uses only ``user32``/``gdi32`` via ctypes — no wx — so it
is safe to call from a worker thread while wx is mid-relayout on the main one.

The grab itself uses the same ``PrintWindow(PW_RENDERFULLCONTENT)`` call as the
screenshot path (so it reads DWM's composition buffer and works even when the
window is occluded), but renders into a raw GDI bitmap and pulls the pixels out
with ``GetDIBits`` instead of going through wx.
"""

from __future__ import annotations

import ctypes
import os
import threading
import time
from ctypes import wintypes

_user32 = ctypes.windll.user32 if os.name == "nt" else None  # type: ignore[attr-defined]
_gdi32 = ctypes.windll.gdi32 if os.name == "nt" else None  # type: ignore[attr-defined]

_PW_RENDERFULLCONTENT = 0x00000002
_DIB_RGB_COLORS = 0
_BI_RGB = 0
_SRCCOPY = 0x00CC0020


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


if _user32 is not None and _gdi32 is not None:
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.GetDC.argtypes = [wintypes.HWND]
    _user32.GetDC.restype = wintypes.HDC
    _user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    _user32.ReleaseDC.restype = ctypes.c_int
    _gdi32.BitBlt.argtypes = [
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HDC,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.DWORD,
    ]
    _gdi32.BitBlt.restype = wintypes.BOOL
    _user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    _user32.PrintWindow.restype = wintypes.BOOL
    _gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
    _gdi32.CreateCompatibleDC.restype = wintypes.HDC
    _gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
    _gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
    _gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
    _gdi32.SelectObject.restype = wintypes.HGDIOBJ
    _gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    _gdi32.DeleteObject.restype = wintypes.BOOL
    _gdi32.DeleteDC.argtypes = [wintypes.HDC]
    _gdi32.DeleteDC.restype = wintypes.BOOL
    _gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        ctypes.POINTER(_BITMAPINFO),
        wintypes.UINT,
    ]
    _gdi32.GetDIBits.restype = ctypes.c_int


def _dibits_from_bitmap(ref_dc: int, mem_dc: int, hbmp: int, w: int, h: int) -> bytes:
    """Pull 32bpp top-down BGRA bytes out of the GDI bitmap selected in mem_dc."""
    bmi = _BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # negative => top-down rows
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = _BI_RGB
    buf = (ctypes.c_char * (w * h * 4))()
    scanned = _gdi32.GetDIBits(ref_dc, hbmp, 0, h, buf, ctypes.byref(bmi), _DIB_RGB_COLORS)
    if scanned == 0:
        return b""
    return bytes(buf)


def grab_window_bgra(hwnd: int) -> tuple[int, int, bytes]:
    """Grab *hwnd* via PrintWindow and return ``(width, height, bgra_bytes)``.

    PrintWindow(PW_RENDERFULLCONTENT) asks the app to **re-render** its current
    widget state through ``WM_PRINT``.  That makes it faithful to the widget
    tree but *not* to the screen: any artefact that lives only in the on-screen
    / DWM surface (e.g. ghost pixels that have not yet been repainted) is erased
    by the fresh render and will not appear in the capture.  Use
    :func:`grab_window_screen_bgra` to capture what is literally on screen.

    Pixels are 32-bit BGRA, top-down.  Returns ``(0, 0, b"")`` on failure.  Pure
    ctypes/GDI — safe to call from any thread.
    """
    if _user32 is None or _gdi32 is None:
        raise RuntimeError("GDI capture is only available on Windows")

    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0, 0, b""
    w = rect.right - rect.left
    h = rect.bottom - rect.top
    if w <= 0 or h <= 0:
        return 0, 0, b""

    screen_dc = _user32.GetDC(hwnd)
    if not screen_dc:
        return 0, 0, b""
    mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
    hbmp = _gdi32.CreateCompatibleBitmap(screen_dc, w, h)
    old = _gdi32.SelectObject(mem_dc, hbmp)
    try:
        if not _user32.PrintWindow(hwnd, mem_dc, _PW_RENDERFULLCONTENT):
            return 0, 0, b""
        data = _dibits_from_bitmap(mem_dc, mem_dc, hbmp, w, h)
        return (w, h, data) if data else (0, 0, b"")
    finally:
        _gdi32.SelectObject(mem_dc, old)
        _gdi32.DeleteObject(hbmp)
        _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(hwnd, screen_dc)


def grab_window_screen_bgra(hwnd: int) -> tuple[int, int, bytes]:
    """Grab the *on-screen pixels* under *hwnd* via a screen-DC BitBlt.

    Unlike :func:`grab_window_bgra` this performs **no re-render**: it copies the
    composited pixels the user actually sees in the window's screen rectangle.
    That is what catches a transient/ghost "third state" that exists only on
    screen and not in the freshly-rendered widget tree.  The trade-off is that
    it reads true screen pixels, so anything occluding the window would corrupt
    the capture (fine when the app under test is the active, top-most window).

    Window-rect coordinates are clamped to >= 0 so a maximised window whose
    frame overhangs the screen edge (position -8,-8) still captures its visible
    client area.  Pixels are 32-bit BGRA, top-down.  Safe to call from any
    thread.
    """
    if _user32 is None or _gdi32 is None:
        raise RuntimeError("GDI capture is only available on Windows")

    rect = wintypes.RECT()
    if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return 0, 0, b""
    left = max(rect.left, 0)
    top = max(rect.top, 0)
    w = rect.right - left
    h = rect.bottom - top
    if w <= 0 or h <= 0:
        return 0, 0, b""

    screen_dc = _user32.GetDC(0)  # DC for the whole (primary) screen
    if not screen_dc:
        return 0, 0, b""
    mem_dc = _gdi32.CreateCompatibleDC(screen_dc)
    hbmp = _gdi32.CreateCompatibleBitmap(screen_dc, w, h)
    old = _gdi32.SelectObject(mem_dc, hbmp)
    try:
        if not _gdi32.BitBlt(mem_dc, 0, 0, w, h, screen_dc, left, top, _SRCCOPY):
            return 0, 0, b""
        data = _dibits_from_bitmap(screen_dc, mem_dc, hbmp, w, h)
        return (w, h, data) if data else (0, 0, b"")
    finally:
        _gdi32.SelectObject(mem_dc, old)
        _gdi32.DeleteObject(hbmp)
        _gdi32.DeleteDC(mem_dc)
        _user32.ReleaseDC(0, screen_dc)


_GRABBERS = {"screen": grab_window_screen_bgra, "printwindow": grab_window_bgra}


class VideoRecorder:
    """Background thread that grabs frames of a window as fast as it can.

    Frames are accumulated in memory as ``(t_seconds, w, h, bgra_bytes)`` where
    ``t_seconds`` is monotonic seconds since :meth:`start`.  Capture stops on
    :meth:`stop` or once ``max_frames`` is reached (a guard against runaway
    memory — at full-window 32bpp each frame is several MB).
    """

    def __init__(
        self,
        hwnd: int,
        *,
        max_frames: int = 240,
        interval_s: float = 0.0,
        method: str = "screen",
    ):
        self.hwnd = hwnd
        self.max_frames = max_frames
        self.interval_s = interval_s
        # "screen" captures literal on-screen pixels (catches ghost/transient
        # artefacts); "printwindow" re-renders the widget tree (hides them).
        self._grab = _GRABBERS.get(method, grab_window_screen_bgra)
        self.frames: list[tuple[float, int, int, bytes]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._t0: float = 0.0

    def start(self) -> None:
        self._t0 = time.monotonic()
        self._thread = threading.Thread(target=self._run, name="video-recorder", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set() and len(self.frames) < self.max_frames:
            t = time.monotonic() - self._t0
            w, h, data = self._grab(self.hwnd)
            if w and h and data:
                self.frames.append((t, w, h, data))
            if self.interval_s:
                time.sleep(self.interval_s)

    def stop(self) -> list[tuple[float, int, int, bytes]]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        return self.frames

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
