"""Shared ``self`` contract that the :class:`DeckPatternsPanel` mixins assume."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol

import wx

if TYPE_CHECKING:
    from services.deck_patterns_service import (
        DeckPatternsService,
        PatternsOptions,
        PatternsResult,
    )
    from utils.background_worker import BackgroundWorker


class DeckPatternsPanelProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckPatternsPanel``."""

    patterns_service: DeckPatternsService
    worker: BackgroundWorker | None
    locale: str | None
    options: PatternsOptions

    zone_cards: dict[str, list[dict[str, Any]]]
    tree: wx.TreeCtrl
    turn_choice: wx.Choice
    status_label: wx.StaticText
    ceiling_label: wx.StaticText
    refresh_button: wx.Button

    _result: PatternsResult | None
    _pending: bool
    _dirty: bool
    _run_token: int
    _on_status_update: Callable[..., None] | None

    def _t(self, key: str, **kwargs: object) -> str: ...
    def selected_turn(self) -> int: ...
    def render(self) -> None: ...
    def recompute(self) -> None: ...
