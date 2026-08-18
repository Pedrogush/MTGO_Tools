"""The Windows dark-mode bridge, and the promise that it never breaks the app.

``widgets/native_dark.py`` calls uxtheme entry points that Microsoft exports by
ordinal and documents nowhere. That is a deliberate trade — it is the only way to
make ``wx.Choice``, checkbox glyphs, list headers and scrollbars dark — but it
means the failure mode has to be "renders exactly like it did before", never an
exception. These tests pin that, and pin the non-Windows behaviour so the module
stays importable off-platform.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

wx = pytest.importorskip("wx")

from widgets import native_dark  # noqa: E402


@pytest.fixture(scope="module")
def app() -> Iterator[object]:
    yield wx.App.Get() or wx.App()


@pytest.fixture
def frame(app: object) -> Iterator[object]:
    window = wx.Frame(None)
    yield window
    window.Destroy()


def test_theme_names_are_the_documented_dark_classes() -> None:
    assert native_dark.THEME_INPUT == "DarkMode_CFD"
    assert native_dark.THEME_EXPLORER == "DarkMode_Explorer"
    assert native_dark.THEME_LIST_HEADER == "ItemsView"


def test_enable_is_idempotent_and_reports_a_bool() -> None:
    first = native_dark.enable_app_dark_mode()
    second = native_dark.enable_app_dark_mode()
    assert isinstance(first, bool)
    assert first == second
    if os.name == "nt":
        assert native_dark.is_app_dark_mode_enabled() is first


def test_apply_dark_theme_never_raises(frame: object) -> None:
    choice = wx.Choice(frame, choices=["a"])
    assert isinstance(native_dark.apply_dark_theme(choice), bool)
    assert isinstance(native_dark.apply_dark_theme(choice, native_dark.THEME_INPUT), bool)


def test_apply_dark_theme_tolerates_an_unknown_theme_class(frame: object) -> None:
    """SetWindowTheme accepts any string; a typo must degrade, not crash."""
    choice = wx.Choice(frame, choices=["a"])
    assert isinstance(native_dark.apply_dark_theme(choice, "NotATheme"), bool)


def test_apply_dark_list_header_never_raises(frame: object) -> None:
    listing = wx.ListCtrl(frame, style=wx.LC_REPORT)
    listing.InsertColumn(0, "Card")
    assert isinstance(native_dark.apply_dark_list_header(listing), bool)


def test_everything_is_a_no_op_without_dark_mode(frame: object, monkeypatch) -> None:
    """The fallback path: pre-1809 Windows, or a build that dropped the ordinals."""
    monkeypatch.setattr(native_dark, "_app_dark_mode_enabled", False)
    choice = wx.Choice(frame, choices=["a"])
    listing = wx.ListCtrl(frame, style=wx.LC_REPORT)
    assert native_dark.apply_dark_theme(choice) is False
    assert native_dark.apply_dark_list_header(listing) is False


def test_enable_reports_failure_when_uxtheme_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(native_dark, "_uxtheme", lambda: None)
    monkeypatch.setattr(native_dark, "_app_dark_mode_enabled", False)
    assert native_dark.enable_app_dark_mode() is False
    assert native_dark.is_app_dark_mode_enabled() is False
