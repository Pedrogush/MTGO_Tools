"""Callable surface of the ``services.gamelog_service`` package.

The gamelog service is function-based — there is no mixin class composing
``self`` state, so this Protocol describes the *module-level* public callables
re-exported from :mod:`services.gamelog_service`. Callers that want to type a
"gamelog service handle" (for dependency injection or test fakes) can target
:class:`GamelogServiceProto` without importing the concrete functions directly.

This Protocol is purely a typing aid and does not change runtime behavior.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from services.card_data_service import CardDataManager


class GamelogServiceProto(Protocol):
    """Public callable surface re-exported from ``services.gamelog_service``."""

    # Top-level orchestrators
    def parse_gamelog_file(
        self,
        file_path: str,
        card_manager: "CardDataManager | None" = ...,
    ) -> dict[str, Any] | None: ...
    def parse_all_gamelogs(
        self,
        directory: str | list[str] | None = ...,
        limit: int | None = ...,
        progress_callback: Any = ...,
        card_manager: "CardDataManager | None" = ...,
    ) -> list[dict[str, Any]]: ...

    # Discovery
    def find_all_gamelog_dirs(self, appdata_base: str | None = ...) -> list[str]: ...
    def find_gamelog_files(
        self, directory: str, since_date: datetime | None = ...
    ) -> list[str]: ...
    def locate_gamelog_directory(self) -> str | None: ...

    # Formats
    def detect_format_from_cards(
        self,
        cards: list[str],
        card_manager: "CardDataManager | None" = ...,
        last_parsed_format: str = ...,
    ) -> str: ...
    def detect_archetype(self, cards: list[str]) -> str: ...

    # Usernames
    def get_current_username(self) -> str | None: ...
    def infer_username_from_matches(self, matches: list[dict[str, Any]]) -> str | None: ...
    def normalize_player_name(self, name: str, to_storage: bool = ...) -> str: ...

    # Parser
    def extract_players(self, content: str) -> list[str]: ...
    def extract_cards_played(self, content: str, player_name: str) -> list[str]: ...
    def parse_timestamp(self, timestamp_str: str, file_path: str | None = ...) -> datetime: ...
    def parse_mulligan_data(self, content: str) -> dict[str, list[int]]: ...
    def parse_match_score(self, content: str) -> tuple[str, int, int] | None: ...
    def parse_game_results(self, content: str) -> list[dict[str, str]]: ...
