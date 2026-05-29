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
from services import mtgo_bridge_service
from services.archetype_resolver import find_archetype_by_name
from services.card_service import get_card_service
from services.collection_service import get_collection_service
from services.comp_rules_service import get_comp_rules_service, linkify_cross_refs
from services.deck_service import get_deck_service
from services.deck_workflow_service import DeckWorkflowService
from services.format_card_pool_service import get_format_card_pool_service
from services.gamelog_service import (
    get_current_username,
    infer_username_from_matches,
    parse_all_gamelogs,
)
from services.image_service import (
    BULK_DATA_CACHE,
    BulkImageDownloader,
    CardImageRequest,
    get_card_image,
    get_image_service,
)
from services.image_service import get_cache as get_image_cache
from services.metagame_service import get_metagame_service
from services.radar_service import get_radar_service
from services.radar_service.card_stats import CardUsageStats
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
from utils.perf import timed

if TYPE_CHECKING:
    from widgets.frames.app_frame import AppFrame


class AppController(
    CardDataMixin,
    ArchetypesMixin,
    DeckManagementMixin,
    CollectionMixin,
    BulkDataMixin,
    SettingsMixin,
    LifecycleMixin,
):

    @timed
    def __init__(
        self,
        *,
        card_service=None,
        deck_service=None,
        metagame_service=None,
        search_service=None,
        collection_service=None,
        image_service=None,
        store_service=None,
        session_manager: DeckSelectorSessionManager | None = None,
        deck_workflow_service: DeckWorkflowService | None = None,
    ):
        ensure_base_dirs()

        self.card_service = card_service or get_card_service()
        self.deck_service = deck_service or get_deck_service()
        self.metagame_service = metagame_service or get_metagame_service()
        self.search_service = search_service or get_search_service()
        self.collection_service = collection_service or get_collection_service()
        self.image_service = image_service or get_image_service()
        self.store_service = store_service or get_store_service()
        self.radar_service = get_radar_service()
        self.comp_rules_service = get_comp_rules_service()
        self.format_card_pool_service = get_format_card_pool_service()
        self.mtgo_bridge_service = mtgo_bridge_service

        # Stateless service functions / constants exposed on the controller so
        # widgets can call them via the controller reference instead of
        # importing from ``services`` directly.
        self.find_archetype_by_name = find_archetype_by_name
        self.parse_all_gamelogs = parse_all_gamelogs
        self.infer_username_from_matches = infer_username_from_matches
        self.get_current_username = get_current_username
        self.linkify_cross_refs = linkify_cross_refs
        self.get_card_image = get_card_image
        self.get_image_cache = get_image_cache
        self.BULK_DATA_CACHE = BULK_DATA_CACHE
        self.BulkImageDownloader = BulkImageDownloader
        self.CardImageRequest = CardImageRequest
        self.CardUsageStats = CardUsageStats

        self.workflow_service = deck_workflow_service or DeckWorkflowService(
            deck_service=self.deck_service,
        )
        self.session_manager = session_manager or DeckSelectorSessionManager(
            deck_repo=self.workflow_service.deck_repo,
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

    # ----- Backward-compat repository accessors -----
    # Widgets, handlers, and a few tests still reach for ``controller.card_repo``,
    # ``controller.deck_repo`` and ``controller.metagame_repo``. Cleaning those
    # call sites is tracked by sibling issues (widgets-no-repo-direct, etc.).
    # Until that cascade is complete, expose the underlying repositories via the
    # owning services so the controller no longer imports ``repositories.*``
    # directly while keeping the existing API working.

    @property
    def card_repo(self):
        return self.card_service.card_repo

    @property
    def deck_repo(self):
        return self.workflow_service.deck_repo

    @property
    def metagame_repo(self):
        return self.metagame_service.metagame_repo
