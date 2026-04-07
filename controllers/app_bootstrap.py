"""Application composition boundary for the deck selector."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from loguru import logger

from controllers.app_controller_helpers import AppControllerUIHelpers
from controllers.bulk_data_helpers import BulkDataHelpers
from controllers.mtgo_background_helpers import MtgoBackgroundHelpers
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
from utils.constants import LOGS_DIR, MTGO_DECKLISTS_ENABLED, ensure_base_dirs
from utils.diagnostics import EventLogger

if TYPE_CHECKING:
    import wx

    from controllers.app_controller import AppController
    from widgets.app_frame import AppFrame


@dataclass(slots=True)
class AppControllerDependencies:
    deck_repo: Any
    metagame_repo: Any
    card_repo: Any
    deck_service: Any
    search_service: Any
    collection_service: Any
    image_service: Any
    store_service: Any
    session_manager: DeckSelectorSessionManager
    deck_workflow_service: DeckWorkflowService
    event_logger: EventLogger
    worker: BackgroundWorker
    bulk_data_helpers: BulkDataHelpers
    mtgo_background_helpers: MtgoBackgroundHelpers


def build_app_controller_dependencies(
    *,
    frame_provider: Callable[[], AppFrame | None],
) -> AppControllerDependencies:
    ensure_base_dirs()

    deck_repo = get_deck_repository()
    metagame_repo = get_metagame_repository()
    card_repo = get_card_repository()
    deck_service = get_deck_service()
    search_service = get_search_service()
    collection_service = get_collection_service()
    image_service = get_image_service()
    store_service = get_store_service()
    session_manager = DeckSelectorSessionManager(deck_repo)
    deck_workflow_service = DeckWorkflowService(
        deck_repo=deck_repo,
        metagame_repo=metagame_repo,
        deck_service=deck_service,
    )
    event_logger = EventLogger(
        LOGS_DIR,
        enabled=session_manager.get_event_logging_enabled(),
    )
    worker = BackgroundWorker()

    return AppControllerDependencies(
        deck_repo=deck_repo,
        metagame_repo=metagame_repo,
        card_repo=card_repo,
        deck_service=deck_service,
        search_service=search_service,
        collection_service=collection_service,
        image_service=image_service,
        store_service=store_service,
        session_manager=session_manager,
        deck_workflow_service=deck_workflow_service,
        event_logger=event_logger,
        worker=worker,
        bulk_data_helpers=BulkDataHelpers(
            image_service=image_service,
            worker=worker,
            frame_provider=frame_provider,
        ),
        mtgo_background_helpers=MtgoBackgroundHelpers(worker=worker),
    )


def create_deck_selector_controller(parent: wx.Window | None = None) -> AppController:
    from controllers.app_controller import AppController, set_deck_selector_controller

    controller: AppController | None = None
    dependencies = build_app_controller_dependencies(
        frame_provider=lambda: controller.frame if controller else None,
    )
    controller = AppController(
        deck_repo=dependencies.deck_repo,
        metagame_repo=dependencies.metagame_repo,
        card_repo=dependencies.card_repo,
        deck_service=dependencies.deck_service,
        search_service=dependencies.search_service,
        collection_service=dependencies.collection_service,
        image_service=dependencies.image_service,
        store_service=dependencies.store_service,
        session_manager=dependencies.session_manager,
        deck_workflow_service=dependencies.deck_workflow_service,
        event_logger=dependencies.event_logger,
        worker=dependencies.worker,
        bulk_data_helpers=dependencies.bulk_data_helpers,
    )
    attach_app_frame(controller, parent=parent)
    start_mtgo_background_fetch(dependencies.mtgo_background_helpers)
    set_deck_selector_controller(controller)
    return controller


def attach_app_frame(
    controller: AppController,
    parent: wx.Window | None = None,
) -> AppFrame:
    import wx

    from widgets.app_frame import AppFrame

    frame = AppFrame(controller=controller, parent=parent)
    callbacks = AppControllerUIHelpers(controller, frame).build_callbacks()
    controller.attach_frame(frame, callbacks)

    wx.CallAfter(frame._restore_session_state)
    wx.CallAfter(lambda: controller.run_initial_loads(deck_save_dir=controller.deck_save_dir))

    return frame


def start_mtgo_background_fetch(helper: MtgoBackgroundHelpers) -> None:
    if MTGO_DECKLISTS_ENABLED:
        helper.start_background_fetch()
    else:
        logger.info("MTGO decklists disabled; skipping background fetch.")
