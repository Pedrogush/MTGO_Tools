"""Shared ``self`` contract that the :class:`DeckHistoryPanel` mixins assume.

The handlers mixin uses :class:`DeckHistoryPanelProto` as a ``TYPE_CHECKING``-only
base so type checkers can see the attributes that :class:`DeckHistoryPanel`
initializes on itself.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import wx

from services.deck_vcs_service import DeckVcsService, GraphCommit
from widgets.panels.deck_history_panel.graph_canvas import DeckGraphCanvas


class DeckHistoryPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckHistoryPanel``."""

    vcs_service: DeckVcsService
    deck_repo: object
    worker: Any
    locale: str | None

    graph_canvas: DeckGraphCanvas
    branch_choice: wx.Choice
    branch_label: wx.StaticText
    preview_tabs: wx.Window
    preview_text: wx.TextCtrl
    diff_text: wx.TextCtrl
    baseline_label: wx.StaticText

    _graph: list[GraphCommit]
    _baseline_sha: str | None
    _selected_sha: str | None
    _last_deck_key: str | None
    _run_token: int
    _refresh_pending: bool

    _on_checkout: Callable[[str], None] | None
    _on_status_update: Callable[..., None] | None
    _on_snapshot: Callable[[Any], None] | None

    def _t(self, key: str, **kwargs: object) -> str: ...

    def current_deck_key(self) -> str: ...

    def current_deck_file(self) -> Path | None: ...

    def refresh_history(self) -> None: ...

    def set_deck_name_text(self, text: str, *, named: bool) -> None: ...

    def Freeze(self) -> None: ...

    def Thaw(self) -> None: ...
