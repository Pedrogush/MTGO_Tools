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

from widgets.notebook import DEFAULT_AGW_STYLE, make_flat_notebook  # noqa: E402


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
    assert _rgb(notebook.GetActiveTabColour()) == T.ACCENT_PRIMARY
    assert _rgb(notebook.GetNonActiveTabTextColour()) == T.TEXT_SECONDARY
    assert _rgb(notebook.GetActiveTabTextColour()) == T.ACCENT_ON_PRIMARY


def test_pages_can_be_added(frame: object) -> None:
    notebook = make_flat_notebook(frame)
    for label in ("Oracle Text", "Stats"):
        notebook.AddPage(wx.Panel(notebook), label)
    assert notebook.GetPageCount() == 2
    assert notebook.GetPageText(1) == "Stats"


def test_a_caller_can_add_to_the_default_style(frame: object) -> None:
    """The deck workspace wants FNB_SMART_TABS; nothing else does."""
    import wx.lib.agw.flatnotebook as fnb

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
