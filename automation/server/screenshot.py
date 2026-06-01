"""Win32 PrintWindow-based screenshot/capture command handlers."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import wx

from automation.server.window_capture import (
    _GWL_EXSTYLE,
    _PW_RENDERFULLCONTENT,
    _SM_CXVIRTUALSCREEN,
    _SM_CYVIRTUALSCREEN,
    _SM_XVIRTUALSCREEN,
    _SM_YVIRTUALSCREEN,
    _SW_HIDE,
    _SW_SHOWNOACTIVATE,
    _SWP_NOACTIVATE,
    _SWP_NOSIZE,
    _SWP_NOZORDER,
    _WS_EX_TOOLWINDOW,
    _save_png_via_pil,
    _user32,
)

if TYPE_CHECKING:
    from automation.server.protocol import AutomationServerProto

    _Base = AutomationServerProto
else:
    _Base = object


class ScreenshotMixin(_Base):
    """Screenshot handlers plus the shared PrintWindow capture machinery."""

    def _handle_screenshot(self, path: str | None = None, headless: bool = False) -> dict[str, Any]:
        """Take a screenshot of the application window.

        Uses the Win32 PrintWindow API (PW_RENDERFULLCONTENT) so the capture
        works even when the window is occluded by other windows.  The *headless*
        parameter is accepted for backward compatibility but is now a no-op —
        PrintWindow is inherently headless.
        """
        import os
        import tempfile
        from datetime import datetime

        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"screenshot_{timestamp}.png"

        # If the requested directory doesn't exist (e.g. /tmp/ passed from WSL),
        # fall back to the system temp directory so SaveFile never shows a dialog.
        save_dir = os.path.dirname(os.path.abspath(path))
        if save_dir and not os.path.isdir(save_dir):
            path = os.path.join(tempfile.gettempdir(), os.path.basename(path))

        bmp = self._capture_window_bitmap(self.frame)
        width, height = bmp.GetWidth(), bmp.GetHeight()

        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        if not _save_png_via_pil(bmp, path):
            raise RuntimeError(f"Failed to save screenshot to {path!r}")

        # Best-effort fsync so the WSL side sees the full file immediately.
        try:
            fd = os.open(path, os.O_RDONLY)
            os.fsync(fd)
            os.close(fd)
        except OSError:
            pass

        return {"path": os.path.abspath(path), "width": width, "height": height}

    def _capture_window_bitmap(self, window: wx.Frame) -> wx.Bitmap:
        """Capture *window* via Win32 PrintWindow and return a wx.Bitmap.

        Works for any wx.Frame — the main AppFrame or any secondary top-level
        window.  Must be called on the wx main thread.  Performs a layout +
        repaint pass and drains the event queue before capturing so DWM has
        finished compositing the window contents.

        If the window is iconized or hidden, it is parked off-screen with the
        WS_EX_TOOLWINDOW style (no taskbar / Alt-Tab entry) and shown there
        with SWP_NOACTIVATE so DWM allocates a composition buffer without the
        user seeing a flash.  Original visibility, position and ex-style are
        restored after the capture.
        """
        if _user32 is None:
            raise RuntimeError("PrintWindow is only available on Windows")

        hwnd = window.GetHandle()
        # Detect via Win32 rather than wx.IsShown()/IsIconized() because the
        # caller may have toggled visibility outside of wx (raw ShowWindow,
        # parent-app coordination, etc.); wx caches its own state and won't
        # reflect those changes.
        was_iconized = bool(_user32.IsIconic(hwnd))
        was_hidden = not bool(_user32.IsWindowVisible(hwnd))
        needs_offscreen = was_iconized or was_hidden

        saved_pos: tuple[int, int] | None = None
        saved_exstyle: int | None = None
        if needs_offscreen:
            saved_pos = tuple(window.GetScreenPosition())
            saved_exstyle = _user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, saved_exstyle | _WS_EX_TOOLWINDOW)
            # Park 100px past the bottom-right of the virtual screen.  Using
            # virtual-screen metrics handles multi-monitor layouts where a
            # hard-coded (-32000, -32000) could land on an actual display.
            x_off = (
                _user32.GetSystemMetrics(_SM_XVIRTUALSCREEN)
                + _user32.GetSystemMetrics(_SM_CXVIRTUALSCREEN)
                + 100
            )
            y_off = (
                _user32.GetSystemMetrics(_SM_YVIRTUALSCREEN)
                + _user32.GetSystemMetrics(_SM_CYVIRTUALSCREEN)
                + 100
            )
            # SetWindowPos on an iconized window updates the restore rect, so
            # the subsequent ShowWindow(SW_SHOWNOACTIVATE) brings it up
            # off-screen rather than at its previous on-screen location.
            _user32.SetWindowPos(
                hwnd,
                0,
                x_off,
                y_off,
                0,
                0,
                _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE,
            )
            # SW_SHOWNOACTIVATE handles both restore-from-minimized and
            # show-from-hidden without stealing focus.  Going through Win32
            # rather than wx.Frame.Show()/Iconize(False) ensures the window
            # state actually flips even if wx's cached IsShown() disagrees.
            _user32.ShowWindow(hwnd, _SW_SHOWNOACTIVATE)

        try:
            # Force a fresh layout and an immediate repaint of the whole widget tree.
            window.Layout()
            window.SendSizeEvent()

            def _refresh_tree(w: wx.Window) -> None:
                w.Refresh(eraseBackground=False)
                w.Update()
                for child in w.GetChildren():
                    _refresh_tree(child)

            _refresh_tree(window)

            # Drain the event queue, sleep for DWM composite, then drain again.
            # Values tuned empirically — shorter sleeps produced half-painted captures.
            for _ in range(5):
                wx.Yield()
            time.sleep(0.15)
            for _ in range(3):
                wx.Yield()

            w, h = window.GetSize()
            bmp = wx.Bitmap(w, h, depth=32)
            mdc = wx.MemoryDC(bmp)
            hdc = mdc.GetHDC()
            ok = _user32.PrintWindow(hwnd, hdc, _PW_RENDERFULLCONTENT)
            mdc.SelectObject(wx.NullBitmap)
            if not ok:
                raise RuntimeError("PrintWindow returned 0 (DWM not compositing?)")
            return bmp
        finally:
            if needs_offscreen:
                # Restore in reverse: original position first (so the
                # restore-rect is correct before we re-iconize/hide), then
                # the visibility state, then the ex-style.
                if saved_pos is not None:
                    _user32.SetWindowPos(
                        hwnd,
                        0,
                        saved_pos[0],
                        saved_pos[1],
                        0,
                        0,
                        _SWP_NOSIZE | _SWP_NOZORDER | _SWP_NOACTIVATE,
                    )
                if was_iconized:
                    window.Iconize(True)
                if was_hidden:
                    _user32.ShowWindow(hwnd, _SW_HIDE)
                if saved_exstyle is not None:
                    _user32.SetWindowLongW(hwnd, _GWL_EXSTYLE, saved_exstyle)

    def _resolve_secondary_window(self, window_name: str) -> wx.Frame | None:
        """Return the live wx.Frame for a named secondary window, or None."""
        attr_map = {
            "opponent_tracker": "tracker_window",
            "timer_alert": "timer_window",
            "match_history": "history_window",
            "metagame": "metagame_window",
            "top_cards": "top_cards_window",
            "mana_keyboard": "mana_keyboard_window",
        }
        attr = attr_map.get(window_name)
        if attr is None:
            return None
        window = getattr(self.frame, attr, None)
        if window is None or not window.IsShown():
            return None
        return window

    def _handle_screenshot_window(
        self, window_name: str, path: str | None = None
    ) -> dict[str, Any]:
        """Take a screenshot of a named secondary top-level window.

        Supported window names: opponent_tracker, timer_alert, match_history,
        metagame, top_cards, mana_keyboard.  The window must already be open
        (use open_widget first if needed).
        """
        import os
        import tempfile
        from datetime import datetime

        window = self._resolve_secondary_window(window_name)
        if window is None:
            available = (
                "opponent_tracker, timer_alert, match_history, metagame, top_cards, mana_keyboard"
            )
            return {
                "error": f"Window {window_name!r} not found or not open. Available: {available}"
            }

        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"window_{window_name}_{ts}.png"

        save_dir = os.path.dirname(os.path.abspath(path))
        if save_dir and not os.path.isdir(save_dir):
            path = os.path.join(tempfile.gettempdir(), os.path.basename(path))

        bmp = self._capture_window_bitmap(window)
        width, height = bmp.GetWidth(), bmp.GetHeight()

        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        if not _save_png_via_pil(bmp, path):
            raise RuntimeError(f"Failed to save window screenshot to {path!r}")

        try:
            fd = os.open(path, os.O_RDONLY)
            os.fsync(fd)
            os.close(fd)
        except OSError:
            pass

        return {"path": os.path.abspath(path), "width": width, "height": height}

    def _handle_screenshot_widget(
        self, widget_name: str, path: str | None = None
    ) -> dict[str, Any]:
        """Take a screenshot cropped to a specific widget's area.

        Captures the full frame via PrintWindow (so occluding windows don't
        corrupt the result) then crops to the widget's position within the frame.
        """
        import os
        import tempfile
        from datetime import datetime

        widget = self._find_mana_widget(widget_name)
        if widget is None:
            return {"error": f"Widget not found: {widget_name}"}

        if path is None:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"widget_{widget_name}_{ts}.png"

        save_dir = os.path.dirname(os.path.abspath(path))
        if save_dir and not os.path.isdir(save_dir):
            path = os.path.join(tempfile.gettempdir(), os.path.basename(path))

        widget_size = widget.GetSize()
        ww, wh = widget_size.width, widget_size.height
        if ww <= 0 or wh <= 0:
            return {"error": f"Widget {widget_name!r} has zero size"}

        # Capture the full frame, then crop to the widget's client-relative rect.
        full_bmp = self._capture_window_bitmap(self.frame)
        fw, fh = full_bmp.GetWidth(), full_bmp.GetHeight()

        # Convert the widget's screen position to frame-client coordinates.
        client_pos = self.frame.ScreenToClient(widget.GetScreenPosition())
        cx = max(0, min(client_pos.x, fw - 1))
        cy = max(0, min(client_pos.y, fh - 1))
        cw = min(ww, fw - cx)
        ch = min(wh, fh - cy)

        img = full_bmp.ConvertToImage()
        cropped = img.GetSubImage(wx.Rect(cx, cy, cw, ch))

        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        if not _save_png_via_pil(cropped, path):
            raise RuntimeError(f"Failed to save widget screenshot to {path!r}")

        try:
            fd = os.open(path, os.O_RDONLY)
            os.fsync(fd)
            os.close(fd)
        except OSError:
            pass

        return {"path": os.path.abspath(path), "width": cw, "height": ch}
