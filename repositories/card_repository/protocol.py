"""Typed protocols for :mod:`repositories.card_repository`.

Two protocols live here:

* :class:`CardRepositoryProto` is the cross-mixin ``self`` contract that the
  :class:`~repositories.card_repository.repository.CardRepository` mixins
  assume. Each mixin uses it as a ``TYPE_CHECKING``-only base so type checkers
  can see the attributes and methods that one mixin reads from ``self`` but
  which are defined on ``CardRepository`` itself or on a sibling mixin.

* :class:`CardDataManagerProto` is the read surface of the card-data manager
  (the in-memory MTGJSON index). Consumers that only need to *query* card
  data should type their dependencies against this protocol instead of
  importing the concrete :class:`CardDataManager`, so they remain easy to
  fake in tests and can't accidentally reach into manager internals.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from repositories.card_repository.schemas import CardEntry

if TYPE_CHECKING:
    from repositories.card_repository.card_data_manager import CardDataManager


class CardRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``CardRepository``."""

    _card_data_manager: CardDataManager | None
    _card_data_loading: bool
    _card_data_ready: bool

    @property
    def card_data_manager(self) -> CardDataManager: ...


class CardDataManagerProto(Protocol):
    """Read surface of a card data manager."""

    data_dir: Path
    index_path: Path
    meta_path: Path

    @property
    def is_loaded(self) -> bool: ...

    def ensure_latest(self, force: bool = ...) -> None: ...
    def get_card(self, name: str) -> CardEntry | None: ...
    def available_formats(self) -> list[str]: ...
    def search_cards(
        self,
        query: str = ...,
        format_filter: str | None = ...,
        type_filter: str | None = ...,
        color_identity: list[str] | None = ...,
        limit: int | None = ...,
    ) -> list[CardEntry]: ...
