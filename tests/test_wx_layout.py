"""Behavioral tests for the runtime-repaint helpers in ``widgets.wx_layout``.

``widgets.wx_layout`` only references ``wx`` for type annotations at import
time and resolves the repaint surface by duck typing, so the helpers run
unchanged against thin test doubles. ``wx`` is not importable in the WSL dev
environment, so a minimal stub module is injected before importing the module
by file path (mirroring the pattern in ``tests/test_deck_results_list.py``).

The companion static guard ``tests/test_layout_repaint_guard.py`` only reads
``relayout``/``set_shown`` as string literals; nothing exercised their actual
runtime branches. These tests cover:

* ``relayout``: lays out the container and forces a top-level repaint, and the
  ``GetTopLevelParent() is None`` no-op branch (no ``Refresh``/``Update``).
* ``set_shown``: the ``changed`` return value, the ``window is None`` no-op,
  and that it always relayouts regardless.

They also give the guard analyzer a positive self-test (a known-bad snippet
*is* flagged) and a negative one (a known-good snippet is *not*), so an
analyzer that regressed to always returning ``[]`` would no longer pass
vacuously.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating attributes on demand.

    ``wx_layout`` only references ``wx`` for type annotations at import time,
    so any attribute access can return a harmless placeholder.
    """

    def __getattr__(self, name: str) -> Any:  # noqa: D401 - simple stub
        value: Any = type(name, (), {})
        setattr(self, name, value)
        return value


def _install_wx_stub() -> types.ModuleType:
    """Install a ``wx`` stub only when the real module is unavailable."""
    try:
        import wx as real_wx  # noqa: F401

        return sys.modules["wx"]
    except Exception:
        pass
    stub = _WxStub("wx")
    sys.modules["wx"] = stub
    return stub


def _load_wx_layout() -> types.ModuleType:
    """Import ``widgets/wx_layout.py`` directly by file path."""
    path = Path(__file__).resolve().parent.parent / "widgets" / "wx_layout.py"
    spec = importlib.util.spec_from_file_location("_wx_layout_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_install_wx_stub()
wx_layout = _load_wx_layout()


class _FakeTopLevel:
    """Records the repaint calls ``relayout`` makes on the owning frame."""

    def __init__(self) -> None:
        self.refresh_calls = 0
        self.update_calls = 0

    def Refresh(self) -> None:
        self.refresh_calls += 1

    def Update(self) -> None:
        self.update_calls += 1


class _FakeWindow:
    """A duck-typed ``wx.Window`` stand-in recording layout/visibility calls."""

    def __init__(self, *, top: _FakeTopLevel | None = None, shown: bool = True) -> None:
        self._top = top
        self._shown = shown
        self.layout_calls = 0
        self.show_calls: list[bool] = []

    def Layout(self) -> None:
        self.layout_calls += 1

    def GetTopLevelParent(self) -> _FakeTopLevel | None:
        return self._top

    def IsShown(self) -> bool:
        return self._shown

    def Show(self, shown: bool) -> None:
        self.show_calls.append(shown)
        self._shown = shown


# ---------------------------------------------------------------------------
# relayout
# ---------------------------------------------------------------------------


def test_relayout_lays_out_and_repaints_top_level():
    top = _FakeTopLevel()
    container = _FakeWindow(top=top)

    wx_layout.relayout(container)

    assert container.layout_calls == 1
    # Refresh() must precede Update() so the invalidated area is flushed; here
    # we only assert both fired exactly once.
    assert top.refresh_calls == 1
    assert top.update_calls == 1


def test_relayout_without_top_level_is_layout_only_no_op():
    container = _FakeWindow(top=None)

    wx_layout.relayout(container)

    # The window still gets laid out, but with no top-level parent there is no
    # frame to repaint, so the helper returns without touching Refresh/Update.
    assert container.layout_calls == 1


def test_relayout_missing_get_top_level_parent_does_not_raise():
    # Duck typing: a container that lacks GetTopLevelParent (a thin double)
    # must still lay out without error and simply skip the repaint.
    class _BareContainer:
        def __init__(self) -> None:
            self.layout_calls = 0

        def Layout(self) -> None:
            self.layout_calls += 1

    container = _BareContainer()
    wx_layout.relayout(container)
    assert container.layout_calls == 1


# ---------------------------------------------------------------------------
# set_shown
# ---------------------------------------------------------------------------


def test_set_shown_reports_change_and_relayouts():
    top = _FakeTopLevel()
    target = _FakeWindow(shown=False)
    container = _FakeWindow(top=top)

    changed = wx_layout.set_shown(target, True, relayout_from=container)

    assert changed is True
    assert target.show_calls == [True]
    assert container.layout_calls == 1
    assert top.refresh_calls == 1
    assert top.update_calls == 1


def test_set_shown_reports_no_change_when_already_in_state():
    top = _FakeTopLevel()
    target = _FakeWindow(shown=True)
    container = _FakeWindow(top=top)

    changed = wx_layout.set_shown(target, True, relayout_from=container)

    assert changed is False
    # Show is still called (idempotent), but visibility did not actually change.
    assert target.show_calls == [True]
    assert container.layout_calls == 1


def test_set_shown_with_none_window_is_relayout_only_no_op():
    top = _FakeTopLevel()
    container = _FakeWindow(top=top)

    changed = wx_layout.set_shown(None, True, relayout_from=container)

    # A not-yet-built optional widget: no visibility change, but the container
    # still relayouts so callers don't need their own None guard.
    assert changed is False
    assert container.layout_calls == 1
    assert top.refresh_calls == 1
    assert top.update_calls == 1


# ---------------------------------------------------------------------------
# Positive/negative self-test of the static guard analyzer.
# ---------------------------------------------------------------------------


def _load_guard() -> types.ModuleType:
    path = Path(__file__).resolve().parent / "test_layout_repaint_guard.py"
    spec = importlib.util.spec_from_file_location("_layout_repaint_guard", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_guard = _load_guard()


def _violations_for_source(tmp_path: Path, source: str) -> list[str]:
    src = tmp_path / "snippet.py"
    src.write_text(source, encoding="utf-8")
    return _guard._violations_in_file(src)


_BAD_SOURCE = """
class Panel:
    def on_toggle(self, advanced):
        self.advanced_panel.Show(advanced)
        self.Layout()
"""

_GOOD_ROUTED_SOURCE = """
from widgets.wx_layout import set_shown

class Panel:
    def on_toggle(self, advanced):
        set_shown(self.advanced_panel, advanced, relayout_from=self)
"""

_GOOD_CONSTRUCTION_SOURCE = """
class Panel:
    def _build(self):
        self.advanced_panel.Show(False)
        self.Layout()
"""


def test_guard_flags_runtime_show_plus_bare_layout(tmp_path):
    violations = _violations_for_source(tmp_path, _BAD_SOURCE)
    assert len(violations) == 1
    assert "on_toggle()" in violations[0]


def test_guard_accepts_method_routed_through_helper(tmp_path):
    assert _violations_for_source(tmp_path, _GOOD_ROUTED_SOURCE) == []


def test_guard_exempts_construction_methods(tmp_path):
    assert _violations_for_source(tmp_path, _GOOD_CONSTRUCTION_SOURCE) == []
