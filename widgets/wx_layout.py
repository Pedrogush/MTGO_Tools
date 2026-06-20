"""Helpers for runtime layout changes that repaint cleanly.

Why this module exists
----------------------
Showing/hiding widgets and re-running ``Layout()`` *at runtime* (collapsing a
panel, toggling advanced filters, swapping a page) does not, on its own, force
the enclosing top-level window to repaint. On Windows (MSW) this leaves "ghost"
pixels behind — most visibly from native ``wx.Button`` controls that were given
a custom background colour (see :func:`widgets.stylize.stylize_button`, which
paints buttons in ``DARK_ACCENT``). The stale rectangle survives until some
*external* event (minimising and restoring the window, or a resize) triggers a
full ``WM_ERASEBKGND`` + repaint.

A bare ``container.Layout()`` after a ``Show``/``Hide`` is therefore latently
buggy *everywhere it appears*, not just at the site where the artefact happened
to be noticed. To make that class of bug impossible by construction, route every
runtime visibility/layout change through the helpers here instead of calling
``Window.Layout()`` directly. They lay the container out and then force the
owning top-level window to erase and repaint immediately — the same thing the
minimise/restore workaround does, but automatically.

Construction-time layout (inside ``__init__``/``_build_*`` before the frame is
shown) does not need these helpers: nothing is on screen yet, so there is no
stale paint to clear.
"""

from __future__ import annotations

import wx


def relayout(container: wx.Window) -> None:
    """Lay out *container* and force a clean repaint of its top-level window.

    Use this instead of a bare ``container.Layout()`` whenever the layout change
    happens in response to user interaction (after the window is on screen).

    The repaint is resolved by duck typing (``GetTopLevelParent``/``Refresh``/
    ``Update``) rather than ``wx.GetTopLevelParent`` so that thin wx Humble-Object
    test doubles — which provide ``Layout`` but not the full window surface — work
    without each having to grow repaint stubs. Real ``wx.Window``s always expose
    these methods, so production always repaints.
    """
    container.Layout()
    get_top = getattr(container, "GetTopLevelParent", None)
    top = get_top() if callable(get_top) else None
    if top is None:
        return
    # Refresh() invalidates the whole client area with background erase; Update()
    # flushes the resulting paint synchronously so no ghost pixels from the
    # previous layout linger.
    refresh = getattr(top, "Refresh", None)
    update = getattr(top, "Update", None)
    if callable(refresh):
        refresh()
    if callable(update):
        update()


def set_shown(window: wx.Window | None, shown: bool, *, relayout_from: wx.Window) -> bool:
    """Show or hide *window*, then relayout *relayout_from* with a clean repaint.

    Returns ``True`` if the visibility actually changed. ``window`` may be
    ``None`` (a not-yet-built optional widget), in which case this is a no-op
    that still relayouts, so callers don't need their own ``None`` guards.
    """
    changed = False
    if window is not None:
        changed = window.IsShown() != shown
        window.Show(shown)
    relayout(relayout_from)
    return changed
