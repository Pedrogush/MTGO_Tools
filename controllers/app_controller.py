"""
Deck Selector Controller - Application logic for the deck selector window.

This controller separates business logic and state management from UI presentation.
It coordinates between services, repositories, and provides a clean interface
for the UI layer to interact with application logic.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    import wx

    from widgets.app_frame import AppFrame

from controllers.app_controller_ui import AppControllerUIBindings
from controllers.bulk_data_coordinator import BulkDataCoordinator
from controllers.mtgo_background_orchestrator import MtgoBackgroundOrchestrator
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
from utils import mtgo_bridge_client
from utils.background_worker import BackgroundWorker
from utils.card_data import CardDataManager
from utils.constants import (
    COLLECTION_CACHE_MAX_AGE_SECONDS,
    GUIDE_STORE,
    MTGO_BRIDGE_SHUTDOWN_TIMEOUT_SECONDS,
    MTGO_BRIDGE_USERNAME_TIMEOUT_SECONDS,
    MTGO_DECKLISTS_ENABLED,
    NOTES_STORE,
    OUTBOARD_STORE,
    ensure_base_dirs,
)


class AppController:

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

        # Services and repositories
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

        # Settings management
        self.current_format = self.session_manager.get_current_format()

        # Deck data source preference
        self._deck_data_source = self.session_manager.get_deck_data_source()

        # Config-backed deck save directory
        self.deck_save_dir = self.session_manager.ensure_deck_save_dir()

        # Application state
        self.archetypes: list[dict[str, Any]] = []
        self.filtered_archetypes: list[dict[str, Any]] = []
        self.zone_cards: dict[str, list[dict[str, Any]]] = {"main": [], "side": [], "out": []}
        self.sideboard_guide_entries: list[dict[str, str]] = []
        self.sideboard_exclusions: list[str] = []
        self.left_mode = self.session_manager.get_left_mode()

        # Thread-safe loading state flags
        self._loading_lock = threading.Lock()
        self.loading_archetypes = False
        self.loading_decks = False
        self.loading_daily_average = False

        # Load stores
        self.notes_store_path = NOTES_STORE
        self.outboard_store_path = OUTBOARD_STORE
        self.guide_store_path = GUIDE_STORE
        self.deck_notes_store = self.store_service.load_store(self.notes_store_path)
        self.outboard_store = self.store_service.load_store(self.outboard_store_path)
        self.guide_store = self.store_service.load_store(self.guide_store_path)

        self._ui_callbacks: dict[str, Callable[..., Any]] = {}

        # Background worker for tasks with lifecycle control
        self._worker = BackgroundWorker()
        self.frame: AppFrame | None = None
        self._bulk_data_coordinator = BulkDataCoordinator(
            image_service=self.image_service,
            worker=self._worker,
            frame_provider=lambda: self.frame,
        )
        self._mtgo_orchestrator = MtgoBackgroundOrchestrator(
            worker=self._worker,
            status_check=self.check_mtgo_bridge_status,
        )

        self.frame = self.create_frame()

        # Start background MTGO data fetch
        if MTGO_DECKLISTS_ENABLED:
            self._mtgo_orchestrator.start_background_fetch()
        else:
            logger.info("MTGO decklists disabled; skipping background fetch.")

    # ============= Card Data Management =============

    def ensure_card_data_loaded(
        self,
        on_success: Callable[[CardDataManager], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
    ) -> None:
        if self.card_repo.get_card_manager() or self.card_repo.is_card_data_loading():
            return

        self.card_repo.set_card_data_loading(True)
        on_status("Loading card database...")

        def worker():
            return self.card_repo.ensure_card_data_loaded()

        def success_handler(manager: CardDataManager):
            self.card_repo.set_card_manager(manager)
            self.card_repo.set_card_data_loading(False)
            self.card_repo.set_card_data_ready(True)
            on_status("Card database loaded")
            on_success(manager)

        def error_handler(error: Exception):
            self.card_repo.set_card_data_loading(False)
            logger.error(f"Failed to load card data: {error}")
            on_status(f"Card database load failed: {error}")
            on_error(error)

        self._worker.submit(worker, on_success=success_handler, on_error=error_handler)

    # ============= Archetype Management =============

    def fetch_archetypes(
        self,
        on_success: Callable[[list[dict[str, Any]]], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
        force: bool = False,
    ) -> None:
        with self._loading_lock:
            if self.loading_archetypes:
                return
            self.loading_archetypes = True

        on_status(f"Loading archetypes for {self.current_format}…")

        def loader(fmt: str):
            return self.workflow_service.fetch_archetypes(fmt, force=force)

        def success_handler(archetypes: list[dict[str, Any]]):
            with self._loading_lock:
                self.loading_archetypes = False
            self.archetypes = archetypes
            self.filtered_archetypes = archetypes
            on_success(archetypes)

        def error_handler(error: Exception):
            with self._loading_lock:
                self.loading_archetypes = False
            logger.error(f"Failed to fetch archetypes: {error}")
            on_error(error)

        self._worker.submit(
            loader,
            self.current_format,
            on_success=success_handler,
            on_error=error_handler,
        )

    def load_decks_for_archetype(
        self,
        archetype: dict[str, Any],
        on_success: Callable[[str, list[dict[str, Any]]], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
    ) -> None:
        with self._loading_lock:
            if self.loading_decks:
                return
            self.loading_decks = True

        name = archetype.get("name", "Unknown")
        on_status(f"Loading decks for {name}…")

        source_filter = self.get_deck_data_source()

        def loader(arch: dict[str, Any]):
            return self.workflow_service.load_decks_for_archetype(arch, source_filter=source_filter)

        def success_handler(decks: list[dict[str, Any]]):
            with self._loading_lock:
                self.loading_decks = False
            self.workflow_service.set_decks_list(decks)
            on_success(name, decks)

        def error_handler(error: Exception):
            with self._loading_lock:
                self.loading_decks = False
            logger.error(f"Failed to load decks: {error}")
            on_error(error)

        self._worker.submit(
            loader,
            archetype,
            on_success=success_handler,
            on_error=error_handler,
        )

    # ============= Deck Management =============

    def download_and_display_deck(
        self,
        deck: dict[str, Any],
        on_success: Callable[[str], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
    ) -> None:
        deck_number = deck.get("number")
        if not deck_number:
            on_error(ValueError("Deck identifier missing"))
            return

        on_status("Downloading deck…")

        source_filter = self.get_deck_data_source()

        def worker(number: str):
            return self.workflow_service.download_deck_text(number, source_filter=source_filter)

        self._worker.submit(worker, deck_number, on_success=on_success, on_error=on_error)

    def build_deck_text(self, zone_cards: dict[str, list[dict[str, Any]]] | None = None) -> str:
        zones = zone_cards if zone_cards is not None else self.zone_cards
        return self.workflow_service.build_deck_text(zones)

    def save_deck(
        self,
        deck_name: str,
        deck_content: str,
        format_name: str,
        deck: dict[str, Any] | None = None,
    ) -> tuple[Path, int | None]:
        return self.workflow_service.save_deck(
            deck_name=deck_name,
            deck_content=deck_content,
            format_name=format_name,
            deck=deck,
            deck_save_dir=self.deck_save_dir,
        )

    def build_daily_average_deck(
        self,
        on_success: Callable[[dict[str, float], int], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
        on_progress: Callable[[int, int], None] | None = None,
    ) -> tuple[bool, str]:
        today = time.strftime("%Y-%m-%d").lower()
        todays_decks = [
            deck
            for deck in self.deck_repo.get_decks_list()
            if today in deck.get("date", "").lower()
        ]

        if not todays_decks:
            return False, "No decks from today found for this archetype."

        with self._loading_lock:
            self.loading_daily_average = True

        on_status("Building daily average deck…")

        source_filter = self.get_deck_data_source()

        def worker(rows: list[dict[str, Any]]):
            return self.workflow_service.build_daily_average_buffer(
                rows,
                source_filter=source_filter,
                on_progress=on_progress,
            )

        def success_handler(buffer: dict[str, float]):
            with self._loading_lock:
                self.loading_daily_average = False
            on_success(buffer, len(todays_decks))

        def error_handler(error: Exception):
            with self._loading_lock:
                self.loading_daily_average = False
            logger.error(f"Daily average error: {error}")
            on_error(error)

        self._worker.submit(
            worker,
            todays_decks,
            on_success=success_handler,
            on_error=error_handler,
        )

        return True, f"Processing {len(todays_decks)} decks"

    # ============= Collection Management =============

    def check_mtgo_bridge_status(self) -> None:
        """Check if MTGO is running and logged in, then update UI button states."""
        callbacks = self._ui_callbacks
        on_mtgo_status = callbacks.get("on_mtgo_status_change")

        mtgo_ready = False
        try:
            payload = mtgo_bridge_client.run_bridge_command(
                "username", timeout=MTGO_BRIDGE_USERNAME_TIMEOUT_SECONDS
            )
            if isinstance(payload, dict):
                username = payload.get("username")
                error = payload.get("error")
                if username and not error:
                    mtgo_ready = True
                    logger.debug(f"MTGO ready: logged in as {username}")
                else:
                    logger.debug(f"MTGO not ready: {error or 'no username'}")
        except mtgo_bridge_client.BridgeCommandError as exc:
            logger.debug(f"MTGO not ready: {exc}")
        except Exception as exc:
            logger.debug(f"MTGO status check failed: {exc}")

        if on_mtgo_status:
            on_mtgo_status(mtgo_ready)

    def load_collection_from_cache(self, directory: Path) -> tuple[bool, dict[str, Any] | None]:
        try:
            info = self.collection_service.load_from_cached_file(directory)
            return True, info
        except (FileNotFoundError, ValueError) as exc:
            logger.debug(f"Could not load collection from cache: {exc}")
            return False, None

    def refresh_collection_from_bridge(
        self, directory: Path | None = None, force: bool = False
    ) -> None:
        callbacks = self._ui_callbacks
        on_status = callbacks.get("on_status", lambda msg: None)
        on_success = callbacks.get("on_collection_refresh_success")
        on_error = callbacks.get("on_collection_failed")
        directory = directory or self.deck_save_dir

        on_status("Fetching collection from MTGO...")
        logger.info("Fetching collection from MTGO Bridge")

        self.collection_service.refresh_from_bridge_async(
            directory=directory,
            force=force,
            on_success=on_success,
            on_error=on_error,
            cache_max_age_seconds=COLLECTION_CACHE_MAX_AGE_SECONDS,
        )

    # ============= Bulk Data Management =============

    def check_and_download_bulk_data(self) -> None:
        self._bulk_data_coordinator.check_and_download_bulk_data(self._ui_callbacks)

    def load_bulk_data_into_memory(
        self, on_status: Callable[[str], None], force: bool = False
    ) -> None:
        self._bulk_data_coordinator.load_bulk_data_into_memory(on_status, force=force)

    def force_bulk_data_update(self) -> None:
        """Force download of bulk data regardless of current state."""
        self._bulk_data_coordinator.force_bulk_data_update(self._ui_callbacks)

    def save_settings(
        self, window_size: tuple[int, int] | None = None, screen_pos: tuple[int, int] | None = None
    ) -> None:
        self.session_manager.save(
            current_format=self.current_format,
            left_mode=self.left_mode,
            deck_data_source=self._deck_data_source,
            zone_cards=self.zone_cards,
            window_size=window_size,
            screen_pos=screen_pos,
        )

    def get_deck_data_source(self) -> str:
        return self._deck_data_source

    def set_deck_data_source(self, source: str) -> None:
        if source not in ("mtggoldfish", "mtgo", "both"):
            logger.warning(f"Invalid deck data source: {source}, defaulting to 'both'")
            source = "both"
        if self._deck_data_source == source:
            return
        self._deck_data_source = source
        self.session_manager.update_deck_data_source(source)

    # ============= Business Logic Methods =============

    def download_deck(
        self,
        deck_number: str,
        on_success: Callable[[str], None],
        on_error: Callable[[Exception], None],
        on_status: Callable[[str], None],
    ) -> None:
        on_status("Downloading deck…")
        source_filter = self.get_deck_data_source()

        def worker(number: str):
            return self.workflow_service.download_deck_text(number, source_filter=source_filter)

        self._worker.submit(worker, deck_number, on_success=on_success, on_error=on_error)

    # ============= State Accessors =============

    def get_current_format(self) -> str:
        return self.current_format

    def set_current_format(self, format_name: str) -> None:
        self.current_format = format_name

    def get_zone_cards(self) -> dict[str, list[dict[str, Any]]]:
        return self.zone_cards

    def get_archetypes(self) -> list[dict[str, Any]]:
        return self.archetypes

    def get_filtered_archetypes(self) -> list[dict[str, Any]]:
        return self.filtered_archetypes

    def set_filtered_archetypes(self, archetypes: list[dict[str, Any]]) -> None:
        self.filtered_archetypes = archetypes

    def get_left_mode(self) -> str:
        return self.left_mode

    def set_left_mode(self, mode: str) -> None:
        self.left_mode = mode

    # ============= Initial Loading Orchestration =============

    def run_initial_loads(self, deck_save_dir: Path, force_archetypes: bool = False) -> None:
        callbacks = self._ui_callbacks

        self.fetch_archetypes(
            on_success=callbacks.get("on_archetypes_success"),
            on_error=callbacks.get("on_archetypes_error"),
            on_status=callbacks.get("on_status"),
            force=force_archetypes,
        )

        # Step 3: Load collection from cache (non-blocking)
        success, info = self.load_collection_from_cache(deck_save_dir)
        if success and info:
            callback = callbacks.get("on_collection_loaded")
            if callback:
                callback(info)
        else:
            callback = callbacks.get("on_collection_not_found")
            if callback:
                callback()

        # Step 4: Check and download bulk data if needed (non-blocking)
        self.check_and_download_bulk_data()

        # Step 5: Check MTGO bridge status and start periodic checking
        self.check_mtgo_bridge_status()
        self._mtgo_orchestrator.start_status_monitoring()

    # ============= Frame Factory =============

    def create_frame(self, parent: wx.Window | None = None) -> AppFrame:
        import wx

        from widgets.app_frame import AppFrame

        # Create the frame
        frame = AppFrame(controller=self, parent=parent)
        self._ui_callbacks = AppControllerUIBindings(self, frame).build_callbacks()

        # Restore UI state from controller's session data
        wx.CallAfter(frame._restore_session_state)

        # Trigger initial loading after frame is ready
        wx.CallAfter(
            lambda: self.run_initial_loads(
                deck_save_dir=self.deck_save_dir,
            )
        )

        return frame

    def shutdown(self, timeout: float = MTGO_BRIDGE_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """Shutdown all background workers gracefully."""
        logger.info("Shutting down AppController background workers...")
        self._worker.shutdown(timeout=timeout)


# Singleton instance
_controller_instance: AppController | None = None


def get_deck_selector_controller() -> AppController:
    global _controller_instance
    if _controller_instance is None:
        _controller_instance = AppController()
    return _controller_instance


def reset_deck_selector_controller() -> None:
    global _controller_instance
    _controller_instance = None
