"""Stateless Win32 screenshot/capture support for the automation server.

Owns the ctypes/Win32 setup and the Pillow-backed PNG save helper.  Kept as a
plain support module (not a mixin) because none of it touches server state.
"""

import ctypes
import os as _os

import wx

# Win32 PrintWindow — the only reliable way to capture a wxFrame on Windows
# 10/11, including when the window is occluded by other windows.  A plain
# ScreenDC/Blit captures screen pixels, so any covering window corrupts the
# result.  PrintWindow asks DWM to render the window's own composition
# buffer directly into a supplied HDC.
_PW_RENDERFULLCONTENT = 0x00000002

# DWM only composites windows that are currently shown and not minimized, so
# capturing a Hide()-d or Iconize()-d frame requires temporarily parking it on
# the virtual desktop where DWM will allocate a composition buffer for it.
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
_SWP_NOSIZE = 0x0001
_SWP_NOZORDER = 0x0004
_SWP_NOACTIVATE = 0x0010
_SM_XVIRTUALSCREEN = 76
_SM_YVIRTUALSCREEN = 77
_SM_CXVIRTUALSCREEN = 78
_SM_CYVIRTUALSCREEN = 79
_SW_HIDE = 0
_SW_SHOWNOACTIVATE = 4  # restore from minimized to most-recent rect, no activate

_user32 = ctypes.windll.user32 if _os.name == "nt" else None  # type: ignore[attr-defined]
if _user32 is not None:
    _user32.PrintWindow.argtypes = [
        ctypes.c_void_p,  # HWND
        ctypes.c_void_p,  # HDC
        ctypes.c_uint,  # flags
    ]
    _user32.PrintWindow.restype = ctypes.c_int
    _user32.SetWindowPos.argtypes = [
        ctypes.c_void_p,  # HWND
        ctypes.c_void_p,  # HWND insert-after
        ctypes.c_int,  # X
        ctypes.c_int,  # Y
        ctypes.c_int,  # cx
        ctypes.c_int,  # cy
        ctypes.c_uint,  # flags
    ]
    _user32.SetWindowPos.restype = ctypes.c_int
    _user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.GetWindowLongW.restype = ctypes.c_long
    _user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    _user32.SetWindowLongW.restype = ctypes.c_long
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int
    _user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    _user32.IsWindowVisible.restype = ctypes.c_int
    _user32.IsIconic.argtypes = [ctypes.c_void_p]
    _user32.IsIconic.restype = ctypes.c_int
    _user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
    _user32.ShowWindow.restype = ctypes.c_int


def _save_png_via_pil(image: "wx.Image | wx.Bitmap", path: str) -> bool:
    """Save *image* as a PNG to *path* via Pillow.

    wxPython's ``Image.SaveFile`` / ``Bitmap.SaveFile`` on MSW opens the
    target file through the wxImage handler chain; on some wxWidgets builds
    that handle is kept alive by the running ``wx.App``, so the file can't
    be unlinked until the app exits (issue #436).  Routing the bytes through
    Pillow's plain ``open()`` avoids the leaked handle.
    """
    from PIL import Image as PilImage

    if isinstance(image, wx.Bitmap):
        wx_img = image.ConvertToImage()
    else:
        wx_img = image
    w, h = wx_img.GetWidth(), wx_img.GetHeight()
    rgb = bytes(wx_img.GetData())
    if wx_img.HasAlpha():
        alpha = bytes(wx_img.GetAlpha())
        pil = PilImage.frombytes("RGB", (w, h), rgb).convert("RGBA")
        pil.putalpha(PilImage.frombytes("L", (w, h), alpha))
    else:
        pil = PilImage.frombytes("RGB", (w, h), rgb)
    try:
        pil.save(path, format="PNG")
    except OSError:
        return False
    return True
