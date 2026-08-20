"""Put Windows' own dark mode behind the controls wx cannot colour.

Why this module exists
----------------------
Phase 1 of the UI redesign (issue #962) set out to theme ``wx.Choice``,
``wx.CheckBox``, ``wx.SpinCtrl`` and ``wx.ListCtrl`` headers dark by setting
colours on them. Measured on wxWidgets 3.2.8 / wxPython 4.2.4, that does not work:

* ``wx.Choice`` ignores **both** ``SetBackgroundColour`` and
  ``SetForegroundColour`` while it is visual-styled — nine construction orders
  were screenshotted and all render the same light grey.
* ``wx.CheckBox`` honours the label colours but the box **glyph** is drawn by the
  theme and stays white — phase 2 replaced the control outright with the
  own-drawn :class:`widgets.checkbox.DarkCheckBox`.
* ``wx.ListCtrl``'s header is a separate native ``SysHeader32``.
  ``SetHeaderAttr`` returns ``True`` and applies only the foreground, which makes
  a white header *less* readable, not more.
* Scrollbars are not reachable from wx at all.

Windows 10 1809+ can draw all four dark itself. The switch is a pair of uxtheme
entry points exported **by ordinal only** — Microsoft ships no headers for them,
but they are stable across every build since 1809 and are what mainstream apps
(Explorer's own dialogs, Notepad++, Windows Terminal's host chrome) use:

``ordinal 133`` ``AllowDarkModeForWindow(HWND, BOOL)``
``ordinal 135`` ``AllowDarkModeForApp(BOOL)`` on 1809, widened to
                ``SetPreferredAppMode(PreferredAppMode)`` on 1903+. Passing ``2``
                means ``ForceDark`` on the newer signature and ``TRUE`` on the
                older one, so one call is correct on both.
``ordinal 136`` ``FlushMenuThemes()`` — repaints menus that already exist.

Everything here is wrapped so that a missing export, a non-Windows platform or a
future Windows that drops the ordinals degrades to exactly today's rendering
rather than raising. :func:`is_app_dark_mode_enabled` lets callers pick a
fallback; :func:`widgets.stylize.disable_native_theme` is the one this app uses.

What the OS theme does **not** reach: the title bar
---------------------------------------------------
``SetPreferredAppMode(ForceDark)`` darkens controls, menus and scrollbars but
leaves every window's **caption** in the light theme -- measured in phase 3b at
``#FFFFFF`` with black text, on the main frame and on a bare probe frame alike,
with and without a menu bar. The caption belongs to DWM, not to uxtheme, and is
switched per-window with ``DwmSetWindowAttribute``; see
:func:`apply_dark_caption`, which every top-level window calls through
:func:`widgets.stylize.init_top_level_window`.

What the OS theme costs us
--------------------------
A dark-mode ``wx.Choice`` is painted in Windows' own ``#333333``, not the app's
``SURFACE_ALT`` (``#282E36``) — the theme owns the control completely, so the
token is advisory there. ``wx.SpinCtrl``, ``wx.CheckBox`` and ``wx.ListCtrl``
keep the app's colours for the parts wx can reach (edit field, label, rows) and
only borrow the theme for the parts it cannot (arrows, box glyph, header).
``wx.Notebook`` is unaffected even by the OS theme, which is why it has to be
migrated to ``FlatNotebook`` instead.
"""

from __future__ import annotations

import ctypes
import os

import wx
from loguru import logger

#: uxtheme ordinals. Named here rather than inline so the (undocumented) numbers
#: appear exactly once.
_ORD_ALLOW_DARK_MODE_FOR_WINDOW = 133
_ORD_SET_PREFERRED_APP_MODE = 135
_ORD_FLUSH_MENU_THEMES = 136

#: ``PreferredAppMode::ForceDark`` — dark regardless of the user's system setting.
#: The app is unconditionally dark, so following the system preference would leave
#: light controls on a dark UI for anyone running Windows in light mode.
_FORCE_DARK = 2

_WM_THEMECHANGED = 0x031A
_LVM_GETHEADER = 0x1000 + 31
#: ``UDM_GETBUDDY``. A wxMSW ``wx.SpinCtrl`` is **two** HWNDs: the control wx
#: hands back from ``GetHandle()`` is the ``msctls_updown32`` arrows, and the
#: text field is a separate ``Edit`` attached to it as its *buddy*. The white
#: client edge belongs to the buddy, which is why ``wx.BORDER_NONE`` on the
#: wx object is a silent no-op -- it lands on the arrows, which never had one.
_UDM_GETBUDDY = 0x0400 + 106

#: ``WS_EX_*`` bits that make Windows draw a sunken/raised non-client frame.
_WS_EX_CLIENTEDGE = 0x00000200
_WS_EX_STATICEDGE = 0x00020000
_WS_EX_WINDOWEDGE = 0x00000100
_GWL_EXSTYLE = -20
#: ``GWL_STYLE`` and the window-style bit a native control sets on itself while
#: it is showing a horizontal scrollbar. The only place that fact is readable --
#: see ``has_horizontal_scrollbar``.
_GWL_STYLE = -16
_WS_HSCROLL = 0x00100000
#: ``SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_FRAMECHANGED`` -- the frame has
#: to be recalculated or the edge stays on screen until something else resizes
#: the control, which is its own species of "the call ran and nothing happened".
_SWP_FRAMECHANGED = 0x0001 | 0x0002 | 0x0004 | 0x0020

#: ``DWMWA_USE_IMMERSIVE_DARK_MODE``. Microsoft moved it: it is attribute **20**
#: on Windows 10 build 18985+ (1903 and later, including every Windows 11) and
#: attribute **19** on 1809-1903 (builds 17763-18984), where 20 returns
#: ``E_INVALIDARG``. Both are tried, 20 first -- the order matters, because on
#: 1903+ attribute 19 is a *different*, valid attribute
#: (``DWMWA_USE_HOSTBACKDROPBRUSH``) that would succeed while doing nothing.
#: Below 1809 neither exists and the caption stays light, which is the
#: documented degradation.
_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_USE_IMMERSIVE_DARK_MODE_1809 = 19

#: Theme class names. ``DarkMode_CFD`` ("common file dialog") is the dark variant
#: for edit/combo controls; ``DarkMode_Explorer`` covers buttons, checkboxes and
#: list views; ``ItemsView`` is what makes a list header dark once the app is in
#: dark mode.
THEME_INPUT = "DarkMode_CFD"
THEME_EXPLORER = "DarkMode_Explorer"
THEME_LIST_HEADER = "ItemsView"

_app_dark_mode_enabled = False


def _uxtheme() -> ctypes.CDLL | None:
    if os.name != "nt":
        return None
    try:
        return ctypes.windll.uxtheme  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - depends on the Windows build
        return None


def enable_app_dark_mode() -> bool:
    """Switch the process into Windows' dark mode. Call once, before any window.

    Ordering matters: controls read the preferred app mode when their HWND is
    created, so a control built before this call keeps the light theme even if
    :func:`apply_dark_theme` is used on it afterwards. The app calls this at the
    top of ``wx.App.OnInit``.

    Returns whether the call went through. Safe to call more than once.
    """
    global _app_dark_mode_enabled
    ux = _uxtheme()
    if ux is None:
        return False
    try:
        set_preferred_app_mode = ux[_ORD_SET_PREFERRED_APP_MODE]
        set_preferred_app_mode.argtypes = [ctypes.c_int]
        set_preferred_app_mode.restype = ctypes.c_int
        set_preferred_app_mode(_FORCE_DARK)
    except Exception as exc:
        logger.debug(f"Windows dark mode unavailable (SetPreferredAppMode): {exc}")
        return False
    try:
        ux[_ORD_FLUSH_MENU_THEMES]()
    except Exception:  # pragma: no cover - cosmetic only, menus repaint anyway
        pass
    _app_dark_mode_enabled = True
    logger.info("Windows dark mode enabled for native controls")
    return True


def is_app_dark_mode_enabled() -> bool:
    """Whether :func:`enable_app_dark_mode` succeeded in this process.

    Call sites use this to choose between the OS dark theme and the classic
    unthemed fallback, so the two never fight over the same control.
    """
    return _app_dark_mode_enabled


def _allow_dark_mode_for_window(handle: int) -> None:
    ux = _uxtheme()
    if ux is None:
        return
    try:
        allow = ux[_ORD_ALLOW_DARK_MODE_FOR_WINDOW]
        allow.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        allow.restype = ctypes.c_bool
        allow(ctypes.c_void_p(handle), True)
    except Exception:  # pragma: no cover - depends on the Windows build
        pass


def _apply_theme_to_handle(handle: int, theme: str) -> bool:
    ux = _uxtheme()
    if ux is None or not handle:
        return False
    _allow_dark_mode_for_window(handle)
    try:
        ux.SetWindowTheme(ctypes.c_void_p(handle), theme, None)
        # The control caches its theme handle at creation, so it has to be told
        # to re-open it; without this the change lands only on the next repaint
        # triggered by something else.
        ctypes.windll.user32.SendMessageW(  # type: ignore[attr-defined]
            ctypes.c_void_p(handle), _WM_THEMECHANGED, 0, 0
        )
    except Exception:  # pragma: no cover - depends on the Windows build
        return False
    return True


def strip_spin_buddy_client_edge(spin: wx.SpinCtrl) -> bool:
    """Remove the ``#FFFFFF`` sunken edge from a ``wx.SpinCtrl``'s text field.

    Measured, after shipping the obvious fix and finding it changed nothing:
    ``strip_native_client_edge`` on a ``wx.SpinCtrl`` is a **silent no-op**. wx
    applies the style flag to ``GetHandle()``, and on wxMSW that returns the
    ``msctls_updown32`` arrows -- ``ex=0x00000000``, no edge to remove. The
    ``Edit`` carrying ``WS_EX_CLIENTEDGE`` is a sibling HWND reachable only
    through ``UDM_GETBUDDY``. Probed on the tracker's four calculator fields:
    the white hairline is still there afterwards, pixel for pixel.

    This is the tenth documented instance of this codebase's signature failure
    and the second one this phase produced -- which is the argument for
    screenshotting a fix rather than reading it.

    Returns whether the buddy was found and its frame recalculated. The arrows
    themselves stay light: phase 1 measured them against ``DarkMode_CFD``, under
    Windows dark mode, and with visual styles disabled entirely, and they are
    light grey in all three.
    """
    if os.name != "nt":
        return False
    try:
        handle = spin.GetHandle()
        if not handle:
            return False
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]
        buddy = user32.SendMessageW(ctypes.c_void_p(handle), _UDM_GETBUDDY, 0, 0)
        if not buddy:
            return False
        style = user32.GetWindowLongW(ctypes.c_void_p(buddy), _GWL_EXSTYLE)
        user32.SetWindowLongW(
            ctypes.c_void_p(buddy),
            _GWL_EXSTYLE,
            style & ~_WS_EX_CLIENTEDGE & ~_WS_EX_STATICEDGE & ~_WS_EX_WINDOWEDGE,
        )
        user32.SetWindowPos(ctypes.c_void_p(buddy), 0, 0, 0, 0, 0, _SWP_FRAMECHANGED)
    except Exception:  # pragma: no cover - depends on the Windows build
        return False
    return True


def has_horizontal_scrollbar(window: wx.Window) -> bool:
    """Whether the native control is *currently showing* a horizontal scrollbar.

    There is no wx-level answer to this, and both of the calls that look like one
    were measured against a bar plainly visible in a screenshot of the builder's
    results list:

    * ``wx.Window.HasScrollbar(wx.HORIZONTAL)`` reads the **wx style** bits, which
      a native control managing its own scrollbars never sets. It answered
      ``False`` with the bar up.
    * ``GetScrollRange(wx.HORIZONTAL)`` answered ``467`` both with the bar up and
      after it had been taken down -- it reports the content width, not the bar.

    The HWND's ``WS_HSCROLL`` bit is the truth, and this is the only route to it.
    Always ``False`` off Windows, where the question does not arise.
    """
    if os.name != "nt":
        return False
    try:
        handle = window.GetHandle()
        if not handle:
            return False
        style = ctypes.windll.user32.GetWindowLongW(  # type: ignore[attr-defined]
            ctypes.c_void_p(handle), _GWL_STYLE
        )
    except Exception:  # pragma: no cover - depends on the Windows build
        return False
    return bool(style & _WS_HSCROLL)


def apply_dark_theme(window: wx.Window, theme: str = THEME_EXPLORER) -> bool:
    """Put one control on a dark Windows theme class. No-op unless dark mode is on."""
    if not _app_dark_mode_enabled:
        return False
    try:
        handle = window.GetHandle()
    except Exception:  # pragma: no cover - defensive
        return False
    return _apply_theme_to_handle(handle, theme)


def apply_dark_caption(window: wx.Window) -> bool:
    """Ask DWM to draw ``window``'s title bar dark. Returns whether it took.

    Deliberately **not** gated on :func:`is_app_dark_mode_enabled`, unlike the
    uxtheme helpers above. Those choose between two ways of theming a control
    and must not fight each other; this one is independent -- the app paints its
    own client area dark whether or not the uxtheme ordinals were available, so
    a light caption is wrong in either case.

    Call it once per top-level window, after ``super().__init__()`` (the HWND has
    to exist) and before ``Show()``. Applying it to a window with no caption --
    the splash frame, the rule popup -- is harmless: DWM returns an error for the
    handle and this returns ``False``.
    """
    if os.name != "nt":
        return False
    try:
        handle = window.GetHandle()
    except Exception:  # pragma: no cover - defensive
        return False
    if not handle:
        return False
    try:
        dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - depends on the Windows build
        return False
    enabled = ctypes.c_int(1)
    for attribute in (_DWMWA_USE_IMMERSIVE_DARK_MODE, _DWMWA_USE_IMMERSIVE_DARK_MODE_1809):
        try:
            result = dwm.DwmSetWindowAttribute(
                ctypes.c_void_p(handle),
                ctypes.c_uint(attribute),
                ctypes.byref(enabled),
                ctypes.sizeof(enabled),
            )
        except Exception:  # pragma: no cover - depends on the Windows build
            return False
        if result == 0:
            return True
    return False


def _enumerate_descendants(handle: int) -> list[tuple[int, str]]:
    """Every descendant HWND of ``handle`` with its Win32 class name."""
    found: list[tuple[int, str]] = []
    if os.name != "nt" or not handle:
        return found
    try:
        user32 = ctypes.windll.user32  # type: ignore[attr-defined]

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        def visit(child: int, _lparam: int) -> bool:
            buffer = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(ctypes.c_void_p(child), buffer, 64)
            found.append((child, buffer.value))
            return True

        user32.EnumChildWindows(ctypes.c_void_p(handle), visit, None)
    except Exception:  # pragma: no cover - depends on the Windows build
        return found
    return found


def apply_dark_native_headers(window: wx.Window) -> int:
    """Darken every native column header nested under ``window``. Returns the count.

    ``wx.dataview.DataViewCtrl`` and ``wx.dataview.TreeListCtrl`` use wx's own
    generic control on MSW, but its column header is still a native
    ``SysHeader32`` child that wx does not expose — so the wrapper can be themed
    and the header stays white. Walking the child HWNDs is the only way to reach
    it, and it covers every current and future header in one call rather than one
    bespoke message per control class.
    """
    if not _app_dark_mode_enabled:
        return 0
    try:
        handle = window.GetHandle()
    except Exception:  # pragma: no cover - defensive
        return 0
    themed = 0
    for child, class_name in _enumerate_descendants(handle):
        if class_name.lower() == "sysheader32" and _apply_theme_to_handle(child, THEME_LIST_HEADER):
            themed += 1
    return themed


def apply_dark_list_header(list_ctrl: wx.ListCtrl) -> bool:
    """Darken a ``wx.ListCtrl``'s header.

    The header is a child ``SysHeader32`` that wx neither creates nor exposes, so
    it has to be fetched with ``LVM_GETHEADER`` and themed on its own. This is the
    only route to a dark list header: ``SetHeaderAttr`` applies the foreground and
    ignores the background, which on the default white header makes things worse.
    """
    if not _app_dark_mode_enabled:
        return False
    if not apply_dark_theme(list_ctrl, THEME_EXPLORER):
        return False
    try:
        header = ctypes.windll.user32.SendMessageW(  # type: ignore[attr-defined]
            ctypes.c_void_p(list_ctrl.GetHandle()), _LVM_GETHEADER, 0, 0
        )
    except Exception:  # pragma: no cover - depends on the Windows build
        return False
    if not header:
        return False
    return _apply_theme_to_handle(header, THEME_LIST_HEADER)


__all__ = [
    "strip_spin_buddy_client_edge",
    "THEME_EXPLORER",
    "THEME_INPUT",
    "THEME_LIST_HEADER",
    "apply_dark_caption",
    "apply_dark_list_header",
    "apply_dark_native_headers",
    "apply_dark_theme",
    "enable_app_dark_mode",
    "has_horizontal_scrollbar",
    "is_app_dark_mode_enabled",
]
