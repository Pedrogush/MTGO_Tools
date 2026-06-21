"""Comprehensive Rules browser frame package."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from widgets.frames.rules_browser.frame import RulesBrowserFrame

__all__ = ["RulesBrowserFrame"]


def __getattr__(name: str) -> Any:
    # Lazily import the wx-dependent frame so that pure-Python submodules
    # (e.g. ``html_render``) can be imported — and unit-tested — without
    # pulling in ``wx`` via this package ``__init__``.
    if name == "RulesBrowserFrame":
        from widgets.frames.rules_browser.frame import RulesBrowserFrame

        return RulesBrowserFrame
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
