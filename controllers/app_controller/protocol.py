"""Shared ``self`` contract that the :class:`AppController` mixins assume."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from controllers.session_manager import DeckSelectorSessionManager
from repositories.card_repository import CardRepository
from repositories.deck_repository import DeckRepository
from repositories.metagame_repository import MetagameRepository
from services.collection_service import CollectionService
from services.deck_service import DeckService
from services.deck_workflow_service import DeckWorkflowService
from services.image_service import ImageService
from services.search_service import SearchService
from utils.background_worker import BackgroundWorker
from utils.diagnostics import EventLogger

if TYPE_CHECKING:
    from controllers.app_controller.ui_callbacks import UICallbacks
    from widgets.frames.app_frame import AppFrame


class AppControllerProto(Protocol):
    """Cross-mixin ``self`` surface for ``AppController``."""

    # Repositories and services
    deck_repo: DeckRepository
    metagame_repo: MetagameRepository
    card_repo: CardRepository
    deck_service: DeckService
    search_service: SearchService
    collection_service: CollectionService
    image_service: ImageService
    store_service: Any  # StoreService — avoiding circular type import
    session_manager: DeckSelectorSessionManager
    workflow_service: DeckWorkflowService

    # Persistent session preferences
    current_format: str
    current_language: str
    _deck_data_source: str
    _average_method: str
    _average_hours: int
    left_mode: str
    event_logger: EventLogger
    deck_save_dir: Path

    # In-memory archetype / deck / sideboard state
    archetypes: list[dict[str, Any]]
    filtered_archetypes: list[dict[str, Any]]
    zone_cards: dict[str, list[dict[str, Any]]]
    sideboard_guide_entries: list[dict[str, str]]
    sideboard_exclusions: list[str]

    # Concurrency / loading flags
    _loading_lock: threading.Lock
    loading_archetypes: bool
    loading_decks: bool
    loading_daily_average: bool

    # Per-deck JSON store paths and in-memory mirrors
    notes_store_path: Path
    outboard_store_path: Path
    guide_store_path: Path
    deck_notes_store: dict[str, Any]
    outboard_store: dict[str, Any]
    guide_store: dict[str, Any]

    # UI / lifecycle handles
    _ui_callbacks: UICallbacks | None
    _worker: BackgroundWorker
    frame: AppFrame | None
    _bulk_check_worker_active: bool

    # Cross-mixin methods
    def fetch_archetypes(
        self,
        on_success: Callable[[list[dict[str, Any]]], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
        force: bool = False,
    ) -> None: ...

    def get_deck_data_source(self) -> str: ...
    def load_bulk_data_into_memory(
        self, on_status: Callable[[str], None], force: bool = False
    ) -> None: ...
    def check_and_download_bulk_data(self) -> None: ...
    def ensure_card_data_loaded(
        self,
        on_success: Callable[..., None],
        on_error: Callable[[Exception], None],
        on_status: Callable[..., None],
    ) -> None: ...
    def load_collection_from_cache(self, directory: Path) -> tuple[bool, dict[str, Any] | None]: ...
    def create_frame(self, parent: Any | None = None) -> AppFrame: ...
