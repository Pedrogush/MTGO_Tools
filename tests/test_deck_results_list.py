"""Tests for the wx-independent bulk-populate logic of the deck results list.

These cover :meth:`DeckResultsListHandlersMixin.set_decks`, the batched
populate that replaces the per-row ``SetItemCount``/``Refresh`` calls so the
916-row deck list triggers exactly one layout/scrollbar recomputation. ``wx`` is
not importable in the WSL dev environment, so a minimal stub module is injected
before importing the handler module by file path.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any


class _WxStub(types.ModuleType):
    """A permissive ``wx`` stand-in fabricating attributes on demand.

    The handlers module only references ``wx`` for type annotations at import
    time, so any attribute access can return a harmless placeholder.
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


def _load_handlers_module() -> types.ModuleType:
    """Import the deck results list ``handlers.py`` directly by file path."""
    path = (
        Path(__file__).resolve().parent.parent
        / "widgets"
        / "lists"
        / "deck_results_list"
        / "handlers.py"
    )
    spec = importlib.util.spec_from_file_location("_drl_handlers_under_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_install_wx_stub()
DeckResultsListHandlersMixin = _load_handlers_module().DeckResultsListHandlersMixin


class _FakeList(DeckResultsListHandlersMixin):
    """Concrete mixin host recording the wx base-class calls under test."""

    def __init__(self) -> None:
        self._items: list[tuple[bool, tuple]] = []
        self.set_item_count_calls: list[int] = []
        self.refresh_calls = 0
        self.freeze_calls = 0
        self.thaw_calls = 0

    def SetItemCount(self, count: int) -> None:
        self.set_item_count_calls.append(count)

    def Refresh(self) -> None:
        self.refresh_calls += 1

    def Freeze(self) -> None:
        self.freeze_calls += 1

    def Thaw(self) -> None:
        self.thaw_calls += 1


def _make_rows(n: int) -> list[tuple[str, str, str, str, str, str]]:
    return [("", f"player{i}", f"arch{i}", f"event{i}", f"result{i}", f"date{i}") for i in range(n)]


def test_set_decks_single_layout_pass() -> None:
    lst = _FakeList()
    rows = _make_rows(916)

    lst.set_decks(rows)

    # Exactly one SetItemCount + Refresh regardless of row count.
    assert lst.set_item_count_calls == [916]
    assert lst.refresh_calls == 1
    # Wrapped in a single Freeze/Thaw pair.
    assert lst.freeze_calls == 1
    assert lst.thaw_calls == 1


def test_set_decks_appends_structured_rows() -> None:
    lst = _FakeList()
    rows = _make_rows(3)

    lst.set_decks(rows)

    assert len(lst._items) == 3
    for (is_structured, data), row in zip(lst._items, rows):
        assert is_structured is True
        assert data == row


def test_set_decks_appends_after_existing_items() -> None:
    lst = _FakeList()
    lst._items.append((False, ("", "preexisting", "")))

    lst.set_decks(_make_rows(2))

    assert len(lst._items) == 3
    assert lst.set_item_count_calls == [3]


def test_set_decks_empty_still_single_pass() -> None:
    lst = _FakeList()

    lst.set_decks([])

    assert lst.set_item_count_calls == [0]
    assert lst.refresh_calls == 1
    assert lst.freeze_calls == 1
    assert lst.thaw_calls == 1
