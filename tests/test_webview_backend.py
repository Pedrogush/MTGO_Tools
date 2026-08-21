"""The deck-stats charts must never render on wx's IE WebView backend.

The bug this pins shipped in 1.2.3 and was visible only in the installed build:
every bar in the Deck Stats tab drew at full panel width, the value labels
centred themselves above the bars instead of sitting beside them, and the Card
Types labels landed on top of their own tracks. Running the same code from
source looked right.

Nothing about the chart code differed. What differed was the backend behind
``wx.html2.WebView``:

* ``WebView.New()`` with the default backend does not fail when WebView2 is
  unavailable on MSW -- it silently returns the **IE** backend, Trident in IE7
  document mode, which has no flexbox. Every ``display:flex`` in the chart CSS
  then collapses to a block, which is exactly the screenshot.
* WebView2 was unavailable in the bundle because ``WebView2Loader.dll`` was not
  in it. wxPython keeps that DLL next to ``wx/_html2*.pyd`` and loads it by bare
  name at runtime, so no extension module imports it and PyInstaller's
  dependency analysis never saw it.

Both halves are guarded here, and neither guard needs a frozen build to run: the
lookup is exercised against a simulated ``sys.frozen`` bundle, the bundling is
read out of the spec, and the backend choice is exercised against a stand-in
``wx.html2``.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import wx
import wx.html2  # noqa: F401  -- ensures ``import wx.html2`` inside the code under test is a no-op

from widgets.charts import view as view_module

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "packaging" / "mtgo_tools.spec"


# ---------------------------------------------------------------------------
# Where the loader DLL is looked for, and where the spec puts it
# ---------------------------------------------------------------------------


def test_loader_path_is_none_from_source() -> None:
    """From source wx finds the DLL beside its own extension module."""
    assert view_module.webview2_loader_path() is None


def test_loader_path_points_into_the_bundle_when_frozen(tmp_path, monkeypatch) -> None:
    """The frozen lookup is the whole fix; simulate the bundle rather than build one."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert view_module.webview2_loader_path() == (
        tmp_path / view_module.WEBVIEW2_LOADER_DEST / view_module.WEBVIEW2_LOADER_NAME
    )


def test_a_bundle_without_the_loader_says_so(tmp_path, monkeypatch) -> None:
    """The old failure was silent. A missing loader now warns and reports False."""
    from loguru import logger

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    messages: list[str] = []
    sink_id = logger.add(messages.append, level="WARNING")
    try:
        loaded = view_module.ensure_webview2_loader()
    finally:
        logger.remove(sink_id)

    assert loaded is False
    assert any(view_module.WEBVIEW2_LOADER_NAME in message for message in messages)


def _spec_constant(name: str) -> str:
    """Read a string constant out of the PyInstaller spec.

    Text-parsed rather than executed: evaluating the spec needs PyInstaller
    imported and a project root on ``sys.path``, and this only has to pin two
    string literals. Same approach as ``tests/test_ci_guards.py``.
    """
    assert SPEC.exists(), f"{SPEC} is missing"
    match = re.search(rf'^{name}\s*=\s*"([^"]+)"', SPEC.read_text(encoding="utf-8"), re.MULTILINE)
    assert match, f"{SPEC} no longer defines {name}"
    return match.group(1)


def test_the_spec_bundles_the_loader_where_the_runtime_looks_for_it() -> None:
    """Bundling it somewhere the lookup does not read would silently reopen the bug."""
    assert _spec_constant("WEBVIEW2_LOADER_NAME") == view_module.WEBVIEW2_LOADER_NAME
    assert _spec_constant("WEBVIEW2_LOADER_DEST") == view_module.WEBVIEW2_LOADER_DEST


def test_the_spec_actually_adds_the_loader_to_the_binaries() -> None:
    """Constants that match but are never used would pass the check above."""
    text = SPEC.read_text(encoding="utf-8")
    assert "binaries += [(str(_webview2_loader), WEBVIEW2_LOADER_DEST)]" in text


# ---------------------------------------------------------------------------
# Which backend the WebView is allowed to come back on
# ---------------------------------------------------------------------------


class _FakeWebView:
    """Stands in for ``wx.html2.WebView`` so the backend choice is inspectable."""

    def __init__(self, available: bool) -> None:
        self.available = available
        self.asked_about: list[object] = []
        self.new_kwargs: dict[str, object] | None = None

    def IsBackendAvailable(self, backend: object) -> bool:  # noqa: N802 - wx spelling
        self.asked_about.append(backend)
        return self.available

    def New(self, parent: object, **kwargs: object) -> str:  # noqa: N802 - wx spelling
        self.new_kwargs = kwargs
        return "webview"


@pytest.fixture
def fake_html2(monkeypatch):
    """Swap ``wx.html2`` for a stand-in, and pin the platform to MSW."""

    def install(*, edge_available: bool) -> _FakeWebView:
        fake_view = _FakeWebView(edge_available)
        module = type(sys)("wx.html2")
        module.WebView = fake_view
        monkeypatch.setattr(wx, "html2", module)
        monkeypatch.setattr(wx, "Platform", "__WXMSW__")
        monkeypatch.delenv(view_module.DISABLE_WEBVIEW_ENV, raising=False)
        return fake_view

    return install


def test_no_webview_at_all_when_edge_is_missing(fake_html2) -> None:
    """The painted fallback is right-but-plain; the IE backend is simply wrong."""
    from loguru import logger

    fake_view = fake_html2(edge_available=False)

    messages: list[str] = []
    sink_id = logger.add(messages.append, level="WARNING")
    try:
        result = view_module.create_webview(parent=None)
    finally:
        logger.remove(sink_id)

    assert result is None, "a WebView on the IE backend must not reach the charts"
    assert fake_view.new_kwargs is None, "WebView.New must not even be attempted"
    assert any("Edge" in message for message in messages)


def test_the_edge_backend_is_requested_by_name(fake_html2) -> None:
    """Defaulting the backend is what let IE through in the first place."""
    fake_view = fake_html2(edge_available=True)

    result = view_module.create_webview(parent=None)

    assert result == "webview"
    assert fake_view.new_kwargs is not None
    assert fake_view.new_kwargs["backend"] == view_module.EDGE_BACKEND
    assert fake_view.asked_about == [view_module.EDGE_BACKEND]


def test_off_msw_the_default_backend_is_fine(fake_html2, monkeypatch) -> None:
    """Only wxMSW has an IE backend to fall back to; WebKit renders the CSS."""
    fake_view = fake_html2(edge_available=False)
    monkeypatch.setattr(wx, "Platform", "__WXGTK__")

    assert view_module.create_webview(parent=None) == "webview"
    assert fake_view.asked_about == [], "no backend probe belongs off MSW"
    assert fake_view.new_kwargs is not None
    assert fake_view.new_kwargs["backend"] == view_module.DEFAULT_BACKEND
