"""The app's single notebook factory.

wxMSW's native ``wx.Notebook`` ignores every colour wx can set on it, so the
redesign's answer is not to theme it but to not use it (issue #962, C3). This
suite guards that decision: it pins the factory's rendering, and it fails if a
``wx.Notebook`` ever reappears in the widget tree.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from utils.constants import theme as T

wx = pytest.importorskip("wx")

import wx.lib.agw.flatnotebook as fnb  # noqa: E402

from widgets.notebook import (  # noqa: E402
    DEFAULT_AGW_STYLE,
    _ThemedTabRenderer,
    make_flat_notebook,
)


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    yield wx.App.Get() or wx.App()


@pytest.fixture
def frame(app: object) -> Iterator[object]:
    window = wx.Frame(None)
    yield window
    window.Destroy()


def _rgb(colour: object) -> tuple[int, int, int]:
    return (colour.Red(), colour.Green(), colour.Blue())


def test_factory_applies_the_tokens(frame: object) -> None:
    notebook = make_flat_notebook(frame)
    assert _rgb(notebook.GetTabAreaColour()) == T.SURFACE_PANEL
    assert _rgb(notebook.GetActiveTabColour()) == T.SELECTION_FILL_ON_PANEL
    assert _rgb(notebook.GetNonActiveTabTextColour()) == T.TEXT_SECONDARY
    assert _rgb(notebook.GetActiveTabTextColour()) == T.SELECTION_TEXT


def test_active_tab_is_the_selection_token_not_a_saturated_fill(frame: object) -> None:
    """Phase 2 owns the accent budget and spent none of it on the tab strip.

    An active tab is a selected item among peers, which is what the selection
    token is for. Two accent-filled tab blocks sat directly above the card art.
    """
    notebook = make_flat_notebook(frame)
    assert _rgb(notebook.GetActiveTabColour()) != T.ACCENT_PRIMARY
    assert _rgb(notebook.GetActiveTabColour()) in set(T.SELECTION_FILLS.values())


def test_pages_can_be_added(frame: object) -> None:
    notebook = make_flat_notebook(frame)
    for label in ("Oracle Text", "Stats"):
        notebook.AddPage(wx.Panel(notebook), label)
    assert notebook.GetPageCount() == 2
    assert notebook.GetPageText(1) == "Stats"


def test_a_caller_can_add_to_the_default_style(frame: object) -> None:
    """The deck workspace wants FNB_SMART_TABS; nothing else does."""
    notebook = make_flat_notebook(frame, agw_style=DEFAULT_AGW_STYLE | fnb.FNB_SMART_TABS)
    assert notebook.GetAGWWindowStyleFlag() & fnb.FNB_SMART_TABS


def test_no_native_notebook_survives_in_the_widget_tree() -> None:
    """wxMSW paints wx.Notebook white and ignores every colour call on it."""
    root = Path(__file__).resolve().parent.parent
    offenders = [
        path.relative_to(root).as_posix()
        for path in (root / "widgets").rglob("*.py")
        if "wx.Notebook(" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], (
        "wx.Notebook renders a light tab strip that no colour call can reach; "
        f"use widgets.notebook.make_flat_notebook instead. Found in: {offenders}"
    )


def test_the_themed_renderer_is_the_one_the_strip_actually_uses(frame: object) -> None:
    """Phase 6: the three colours FlatNotebook exposes no setter for.

    ``GetRenderer`` resolves the style to an entry in a per-notebook
    ``FNBRendererMgr``, so installing on ``-1`` is only correct as long as the
    app's style bits do not select one of the named renderers.
    """
    notebook = make_flat_notebook(frame, agw_style=DEFAULT_AGW_STYLE | fnb.FNB_SMART_TABS)
    renderer = notebook._pages._mgr.GetRenderer(notebook.GetAGWWindowStyleFlag())
    assert isinstance(renderer, _ThemedTabRenderer)


def test_the_strip_border_the_library_would_have_drawn_is_white(frame: object) -> None:
    """The reason :class:`_ThemedTabRenderer` exists, pinned as an assertion.

    ``PageContainer.GetSingleLineBorderColour`` returns a hard-coded ``wx.WHITE``
    for every style except ``FNB_FANCY_TABS`` (which phase 1 removed), and
    ``DrawTabsLine`` fills two full-width rectangles with it. If a future wxPython
    ever makes this settable, this test fails and the override can be simplified.
    """
    notebook = make_flat_notebook(frame)
    assert _rgb(notebook._pages.GetSingleLineBorderColour()) == (255, 255, 255)


def test_the_tab_container_background_is_dark(frame: object) -> None:
    """``DrawTabs`` strokes the strip's outline in the *container's* background.

    Left at the wx default that is #F0F0F0, which is how a fully "themed"
    notebook still came framed in a near-white hairline.
    """
    notebook = make_flat_notebook(frame)
    assert _rgb(notebook._pages.GetBackgroundColour()) == T.SURFACE_PANEL
