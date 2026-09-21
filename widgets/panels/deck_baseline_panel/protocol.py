"""Shared ``self`` contract the baseline panel's mixins assume.

The handlers mixin references attributes built in :class:`DeckBaselinePanel`'s
constructor; this gives a type checker something to resolve them against
without changing the runtime MRO.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

import wx


class DeckBaselinePanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckBaselinePanel``."""

    baseline_service: Any
    worker: Any
    locale: str | None

    # Widgets built by the panel.
    target_label: wx.StaticText
    status_label: wx.StaticText
    tree: wx.TreeCtrl

    # Mutable run state, all initialized on the panel itself.
    _baseline: Any
    _pending: bool
    _computed_for: tuple[str, str] | None
    _run_token: int

    # Supplied by the frame so the tab follows the app's own selection rather
    # than carrying a second pair of format/archetype pickers.
    _archetype_provider: Callable[[], dict[str, Any] | None] | None
    _format_provider: Callable[[], str] | None
    _on_status_update: Callable[..., None] | None

    def _t(self, key: str, **kwargs: object) -> str: ...

    def IsShownOnScreen(self) -> bool: ...
