"""AppController composed from responsibility-specific mixins."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

from controllers.app_controller.archetypes import ArchetypesMixin
from controllers.app_controller.bulk_data import BulkDataMixin
from controllers.app_controller.card_data import CardDataMixin
from controllers.app_controller.collection import CollectionMixin
from controllers.app_controller.decks import DeckManagementMixin
from controllers.app_controller.lifecycle import LifecycleMixin
from controllers.app_controller.settings import SettingsMixin
from controllers.app_controller.ui_callbacks import UICallbacks
from controllers.session_manager import DeckSelectorSessionManager
from repositories.card_repository import get_card_repository
from repositories.deck_repository import get_deck_repository
from repositories.metagame_repository import get_metagame_repository
from services.collection_service import get_collection_service
from services.deck_service import get_deck_service
from services.deck_workflow_service import DeckWorkflowService
from services.image_service import get_image_service
from services.search_service import get_search_service
from services.store_service import get_store_service
from utils.background_worker import BackgroundWorker
from utils.constants import (
    GUIDE_STORE,
    LOGS_DIR,
    NOTES_STORE,
    OUTBOARD_STORE,
    ensure_base_dirs,
)
from utils.diagnostics import EventLogger

if TYPE_CHECKING:
    from widgets.app_frame import AppFrame


class AppController(
    CardDataMixin,
    ArchetypesMixin,
    DeckManagementMixin,
    CollectionMixin,
    BulkDataMixin,
    SettingsMixin,
    LifecycleMixin,
):

    def __init__(
        self,
        *,
        deck_repo=None,
        metagame_repo=None,
        card_repo=None,
        deck_service=None,
        search_service=None,
        collection_service=None,
        image_service=None,
        store_service=None,
        session_manager: DeckSelectorSessionManager | None = None,
        deck_workflow_service: DeckWorkflowService | None = None,
    ):
        ensure_base_dirs()

        self.deck_repo = deck_repo or get_deck_repository()
        self.metagame_repo = metagame_repo or get_metagame_repository()
        self.card_repo = card_repo or get_card_repository()
        self.deck_service = deck_service or get_deck_service()
        self.search_service = search_service or get_search_service()
        self.collection_service = collection_service or get_collection_service()
        self.image_service = image_service or get_image_service()
        self.store_service = store_service or get_store_service()

        self.session_manager = session_manager or DeckSelectorSessionManager(self.deck_repo)
        self.workflow_service = deck_workflow_service or DeckWorkflowService(
            deck_repo=self.deck_repo,
            metagame_repo=self.metagame_repo,
            deck_service=self.deck_service,
        )

        self.current_format = self.session_manager.get_current_format()
        self.current_language = self.session_manager.get_language()

        self._deck_data_source = self.session_manager.get_deck_data_source()
        self._average_method = self.session_manager.get_average_method()
        self._average_hours = self.session_manager.get_average_hours()

        self.event_logger = EventLogger(
            LOGS_DIR,
            enabled=self.session_manager.get_event_logging_enabled(),
        )

        self.deck_save_dir = self.session_manager.ensure_deck_save_dir()

        self.archetypes: list[dict[str, Any]] = []
        self.filtered_archetypes: list[dict[str, Any]] = []
        self.zone_cards: dict[str, list[dict[str, Any]]] = {"main": [], "side": [], "out": []}
        self.sideboard_guide_entries: list[dict[str, str]] = []
        self.sideboard_exclusions: list[str] = []
        self.left_mode = self.session_manager.get_left_mode()

        self._loading_lock = threading.Lock()
        self.loading_archetypes = False
        self.loading_decks = False
        self.loading_daily_average = False

        self.notes_store_path = NOTES_STORE
        self.outboard_store_path = OUTBOARD_STORE
        self.guide_store_path = GUIDE_STORE
        self.deck_notes_store = self.store_service.load_store(self.notes_store_path)
        self.outboard_store = self.store_service.load_store(self.outboard_store_path)
        self.guide_store = self.store_service.load_store(self.guide_store_path)

        self._ui_callbacks: UICallbacks | None = None

        self._worker = BackgroundWorker()
        self.frame: AppFrame | None = None
        self._bulk_check_worker_active = False

        self.frame = self.create_frame()
