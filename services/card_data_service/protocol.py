"""Public surface of the ``services.card_data_service`` package.

``CardDataManagerProto`` describes the methods callers actually use against
a card data manager, so dependency injection / test fakes can target a typed
interface instead of importing the concrete :class:`CardDataManager`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from services.card_data_service.schemas import CardEntry


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
