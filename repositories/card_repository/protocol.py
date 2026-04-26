"""Shared ``self`` contract that the :class:`CardRepository` mixins assume.

Each mixin in this package uses :class:`CardRepositoryProto` as a
``TYPE_CHECKING``-only base so that type checkers can see the attributes
and methods that one mixin reads from ``self`` but which are defined on
``CardRepository`` itself or on a sibling mixin.
"""

from __future__ import annotations

from typing import Protocol

from utils.card_data import CardDataManager


class CardRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardRepository``."""

    _card_data_manager: CardDataManager | None
    _card_data_loading: bool
    _card_data_ready: bool

    @property
    def card_data_manager(self) -> CardDataManager: ...
