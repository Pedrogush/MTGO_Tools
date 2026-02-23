"""Tests for wx-independent methods of CardBoxPanel.

These tests cover pure-Python logic that does not require a wx display or
event loop. wx is stubbed out via sys.modules so the tests run in headless
CI environments without wxPython installed.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from typing import Any
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Stub wx BEFORE importing any wx-dependent module.
# card_box_panel.py is loaded directly (bypassing widgets/panels/__init__.py)
# to avoid pulling in unrelated panel modules that have additional
# transitive dependencies (bs4, services, etc.).
# ---------------------------------------------------------------------------
if "wx" not in sys.modules:
    _wx_stub = MagicMock()
    # wx.Panel must be a real Python class so CardBoxPanel can inherit from it.
    _wx_stub.Panel = type("_WxPanel", (object,), {})
    sys.modules["wx"] = _wx_stub


def _load_card_box_panel_module():
    """Load widgets/panels/card_box_panel.py directly, bypassing the package __init__."""
    import pathlib

    src = pathlib.Path(__file__).parent.parent / "widgets" / "panels" / "card_box_panel.py"
    spec = importlib.util.spec_from_file_location("widgets.panels.card_box_panel", src)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["widgets.panels.card_box_panel"] = mod
    spec.loader.exec_module(mod)
    return mod


_cbp_mod = _load_card_box_panel_module()
CardBoxPanel = _cbp_mod.CardBoxPanel


# ---------------------------------------------------------------------------
# _build_image_name_candidates
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "card, meta, expected",
    [
        ({"name": "Island"}, {}, ["Island"]),
        ({"name": "A // B"}, {}, ["A // B"]),
        ({"name": "A"}, {"aliases": ["Alias1"]}, ["A", "Alias1"]),
        ({"name": "A"}, {"aliases": ["A // B", "Other"]}, ["A", "A // B", "Other"]),
        ({"name": "A"}, {"aliases": "bad"}, ["A"]),
        ({"name": ""}, {}, []),
    ],
    ids=[
        "simple-card",
        "dfc-combined-name",
        "non-dfc-alias",
        "dfc-alias-promoted",
        "non-list-aliases",
        "empty-name",
    ],
)
def test_build_image_name_candidates(
    card: dict[str, Any], meta: dict[str, Any], expected: list[str]
) -> None:
    """_build_image_name_candidates must return the correct candidate list for each input."""
    result = CardBoxPanel._build_image_name_candidates(None, card, meta)
    assert result == expected


# ---------------------------------------------------------------------------
# preload_image
# ---------------------------------------------------------------------------
def test_preload_image_calls_refresh_exactly_once() -> None:
    """preload_image() must delegate to _refresh_card_bitmap exactly once."""
    stub = types.SimpleNamespace(_image_attempted=False)
    call_count = 0

    def fake_refresh() -> None:
        nonlocal call_count
        call_count += 1
        stub._image_attempted = True

    stub._refresh_card_bitmap = fake_refresh

    CardBoxPanel.preload_image(stub)
    CardBoxPanel.preload_image(stub)  # second call — must be a no-op

    assert call_count == 1


def test_preload_image_skips_if_already_attempted() -> None:
    """preload_image() must not call _refresh_card_bitmap when _image_attempted is True."""

    def _raise_if_called() -> None:
        raise AssertionError("_refresh_card_bitmap must not be called")

    stub = types.SimpleNamespace(_image_attempted=True, _refresh_card_bitmap=_raise_if_called)
    CardBoxPanel.preload_image(stub)  # must not raise
