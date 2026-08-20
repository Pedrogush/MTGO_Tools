"""The app's one notebook widget.

wxMSW's ``wx.Notebook`` is a native tab control: it ignores
``SetBackgroundColour`` and ``SetForegroundColour`` entirely, so a dark app gets a
white tab strip with black text and there is no colour call that fixes it. The
only route to a dark notebook is a generic (fully wx-drawn) one, which is what
``wx.lib.agw.flatnotebook`` is — and what the deck workspace has always used.

Phase 1 (issue #962, C3 / §4.3) removes the last ``wx.Notebook`` in the tree, in
the card panel, which sat about 400px from a themed ``FlatNotebook``. This module
is the shared factory so the two cannot drift apart again.
"""

from __future__ import annotations

import wx
from wx.lib.agw import flatnotebook as fnb

from utils.constants.theme import (
    ACCENT_ON_PRIMARY,
    ACCENT_PRIMARY,
    SURFACE_BASE,
    SURFACE_PANEL,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

#: No close button, no navigation arrows, and — importantly — **not**
#: ``FNB_FANCY_TABS``. Fancy tabs draw the active tab as a light system gradient
#: and ignore ``SetActiveTabColour`` entirely, so the deck workspace has been
#: rendering a white tab on a dark strip ever since it set that colour. The plain
#: tab renderer honours it, which is the difference between "themed" and "themed
#: except for the one tab you are looking at".
#:
#: ``FNB_SMART_TABS`` is deliberately not in the default either — it adds a
#: Ctrl+Tab overlay that only makes sense for the multi-tab deck workspace, which
#: passes its own style.
DEFAULT_AGW_STYLE = fnb.FNB_NO_X_BUTTON | fnb.FNB_NO_NAV_BUTTONS


def stylize_notebook(notebook: fnb.FlatNotebook) -> None:
    """Paint a ``FlatNotebook`` with the app's tokens."""
    notebook.SetTabAreaColour(wx.Colour(*SURFACE_PANEL))
    notebook.SetActiveTabColour(wx.Colour(*ACCENT_PRIMARY))
    notebook.SetNonActiveTabTextColour(wx.Colour(*TEXT_SECONDARY))
    notebook.SetActiveTabTextColour(wx.Colour(*ACCENT_ON_PRIMARY))
    notebook.SetBackgroundColour(wx.Colour(*SURFACE_BASE))
    notebook.SetForegroundColour(wx.Colour(*TEXT_PRIMARY))


def make_flat_notebook(
    parent: wx.Window,
    *,
    agw_style: int | None = None,
) -> fnb.FlatNotebook:
    """Build a themed ``FlatNotebook``. The only notebook constructor in the app."""
    notebook = fnb.FlatNotebook(
        parent,
        agwStyle=DEFAULT_AGW_STYLE if agw_style is None else agw_style,
    )
    stylize_notebook(notebook)
    return notebook


__all__ = ["DEFAULT_AGW_STYLE", "make_flat_notebook", "stylize_notebook"]
