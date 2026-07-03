"""Shared application window icon (title bar + taskbar) for top-level frames.

The PyInstaller ``icon=`` only sets the icon of the .exe file itself (what
Explorer shows). The icon a window shows in its title bar and on the taskbar is
set at runtime via ``wx.TopLevelWindow.SetIcons``; without it wx falls back to
its default. This module loads the bundled app icon once and applies it to any
frame that asks.
"""

from __future__ import annotations

import wx
from loguru import logger

from utils.constants.paths import resource_path

# Must match the icon wired into packaging/mtgo_tools.spec and installer.iss,
# and be bundled as data by the spec so resource_path() can find it when frozen.
_APP_ICON_PARTS = ("assets", "icons", "hammer.ico")

_bundle: wx.IconBundle | None = None
_loaded = False


def _load_bundle() -> wx.IconBundle | None:
    global _bundle, _loaded
    if _loaded:
        return _bundle
    _loaded = True
    path = resource_path(*_APP_ICON_PARTS)
    try:
        if not path.exists():
            logger.debug("App icon not found at {}", path)
            return None
        bundle = wx.IconBundle(str(path), wx.BITMAP_TYPE_ICO)
        if bundle.GetIcon(wx.Size(32, 32)).IsOk():
            _bundle = bundle
    except Exception as exc:  # pragma: no cover - defensive; never block the UI
        logger.debug("Could not load app icon from {}: {}", path, exc)
    return _bundle


def apply_app_icon(frame: wx.TopLevelWindow) -> None:
    """Set the title-bar / taskbar icon on a top-level frame, if available."""
    bundle = _load_bundle()
    if bundle is not None:
        frame.SetIcons(bundle)
