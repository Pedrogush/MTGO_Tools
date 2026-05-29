"""Tests for the deck builder result-list copy hotkeys (1-4 main, Shift+1-4 side).

These cover the wx-independent dispatch logic in
:class:`DeckBuilderPanelHandlersMixin`. ``wx`` is not importable in the
WSL dev environment, so a minimal stub module is injected before importing
the handlers mixin. The stub provides only the attributes the module touches
at import time and during the exercised code paths.
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest


class _WxStub(types.ModuleType):
    """A ``wx`` stand-in that fabricates unique int constants on demand.

    Importing the deck builder package transitively touches many ``wx`` names
    (``WXK_TAB``, ``LIST_FORMAT_LEFT``, widget classes used as bases, ...).
    Rather than enumerate them, unknown attribute reads return a fresh unique
    integer so any constant comparison is well-defined. The numpad digit codes
    are pinned to values distinct from the top-row ``ord("1")..ord("4")`` keys
    so the digit map under test behaves like the real wx.
    """

    # Mirror the real wx values so the stub matches the constants the handler
    # reads on the Windows host (wx.WXK_NUMPAD0 == 324, NUMPAD1..9 == 325..333).
    _PINNED = {
        "NOT_FOUND": -1,
        "WXK_NUMPAD1": 325,
        "WXK_NUMPAD2": 326,
        "WXK_NUMPAD3": 327,
        "WXK_NUMPAD4": 328,
    }

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self._counter = 1000

    def __getattr__(self, item: str) -> Any:
        if item in self._PINNED:
            value = self._PINNED[item]
        else:
            # Unique int per name; widget base classes resolve to ``object``.
            self._counter += 1
            value = self._counter
        setattr(self, item, value)
        return value


def _install_wx_stub() -> types.ModuleType:
    """Install a permissive ``wx`` stub only when real ``wx`` is unavailable.

    On the Windows host where real ``wx`` imports fine, the stub is never
    installed (so it cannot poison other tests). In the WSL dev environment
    ``import wx`` fails, so the stub stands in for the constants this test
    needs.
    """
    try:
        import wx as real_wx  # noqa: F401

        return sys.modules["wx"]
    except Exception:
        pass
    existing = sys.modules.get("wx")
    if isinstance(existing, _WxStub):
        return existing
    wx = _WxStub("wx")
    sys.modules["wx"] = wx
    return wx


def _load_handlers_module() -> types.ModuleType:
    """Import ``handlers.py`` directly, bypassing the package ``__init__``.

    The deck builder package ``__init__`` transitively imports ``wx.svg`` and
    real widget classes, which the stub cannot satisfy. ``handlers.py`` itself
    only needs ``wx`` plus ``utils.constants``, so load it by file path.
    """
    import importlib.util
    from pathlib import Path

    path = (
        Path(__file__).resolve().parent.parent
        / "widgets"
        / "panels"
        / "deck_builder_panel"
        / "handlers.py"
    )
    spec = importlib.util.spec_from_file_location("_db_handlers_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_WX = _install_wx_stub()
DeckBuilderPanelHandlersMixin = _load_handlers_module().DeckBuilderPanelHandlersMixin


class _KeyEvent:
    """Stand-in for ``wx.KeyEvent`` exposing the methods the handler calls."""

    def __init__(
        self,
        key_code: int,
        *,
        shift: bool = False,
        ctrl: bool = False,
        alt: bool = False,
    ) -> None:
        self._key_code = key_code
        self._shift = shift
        self._ctrl = ctrl
        self._alt = alt
        self.skipped = False

    def GetKeyCode(self) -> int:
        return self._key_code

    def ShiftDown(self) -> bool:
        return self._shift

    def ControlDown(self) -> bool:
        return self._ctrl

    def AltDown(self) -> bool:
        return self._alt

    def Skip(self) -> None:
        self.skipped = True


class _ResultsCtrl:
    def __init__(self, first_selected: int = 0) -> None:
        self._first_selected = first_selected

    def GetFirstSelected(self) -> int:
        return self._first_selected


class _Panel(DeckBuilderPanelHandlersMixin):
    """Concrete subclass wiring just enough state for the hotkey paths."""

    def __init__(self, selected: dict[str, Any] | None) -> None:
        self._selected = selected
        self.results_ctrl = _ResultsCtrl()
        self.main_calls: list[tuple[str, int]] = []
        self.side_calls: list[tuple[str, int]] = []
        self.active_zone_calls: list[str] = []
        self._on_add_to_main = lambda name, count=1: self.main_calls.append((name, count))
        self._on_add_to_side = lambda name, count=1: self.side_calls.append((name, count))
        self._on_add_to_active_zone = self.active_zone_calls.append

    def get_selected_result(self) -> dict[str, Any] | None:
        return self._selected

    def get_result_at_index(self, idx: int) -> dict[str, Any] | None:
        return self._selected


@pytest.mark.parametrize(
    "key_code, expected",
    [
        (ord("1"), 1),
        (ord("2"), 2),
        (ord("3"), 3),
        (ord("4"), 4),
        # Reference the same wx constants the handler reads, so the codes stay
        # correct under both real wx (Windows) and the stub (WSL) rather than
        # hard-coding numbers that drift from wx's actual numpad values.
        (_WX.WXK_NUMPAD1, 1),
        (_WX.WXK_NUMPAD4, 4),
        (ord("0"), None),
        (ord("5"), None),
        (ord("a"), None),
    ],
)
def test_digit_to_count(key_code: int, expected: int | None) -> None:
    assert DeckBuilderPanelHandlersMixin._digit_to_count(key_code) == expected


@pytest.mark.parametrize("count_key, count", [(ord("1"), 1), (ord("4"), 4)])
def test_digit_adds_copies_to_main(count_key: int, count: int) -> None:
    panel = _Panel({"name": "Llanowar Elves"})
    event = _KeyEvent(count_key)
    panel._on_result_key_down(event)
    assert panel.main_calls == [("Llanowar Elves", count)]
    assert panel.side_calls == []
    assert event.skipped is False


@pytest.mark.parametrize("count_key, count", [(ord("2"), 2), (ord("3"), 3)])
def test_shift_digit_adds_copies_to_side(count_key: int, count: int) -> None:
    panel = _Panel({"name": "Pyroblast"})
    event = _KeyEvent(count_key, shift=True)
    panel._on_result_key_down(event)
    assert panel.side_calls == [("Pyroblast", count)]
    assert panel.main_calls == []


def test_plus_adds_one_to_active_zone() -> None:
    panel = _Panel({"name": "Island"})
    event = _KeyEvent(ord("+"))
    panel._on_result_key_down(event)
    assert panel.active_zone_calls == ["Island"]
    assert panel.main_calls == []
    assert panel.side_calls == []


def test_no_selection_does_nothing() -> None:
    panel = _Panel(None)
    event = _KeyEvent(ord("3"))
    panel._on_result_key_down(event)
    assert panel.main_calls == []
    assert panel.side_calls == []


def test_ctrl_digit_is_skipped() -> None:
    """Ctrl-modified digits are left for the global app hotkey handler."""
    panel = _Panel({"name": "Island"})
    event = _KeyEvent(ord("1"), ctrl=True)
    panel._on_result_key_down(event)
    assert panel.main_calls == []
    assert event.skipped is True


def test_unmapped_key_is_skipped() -> None:
    panel = _Panel({"name": "Island"})
    event = _KeyEvent(ord("z"))
    panel._on_result_key_down(event)
    assert event.skipped is True
