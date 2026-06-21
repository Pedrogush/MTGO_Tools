"""Handler mixins composed into :class:`AppFrame`."""

from widgets.frames.app_frame.handlers.app_frame import AppFrameHandlersMixin
from widgets.frames.app_frame.handlers.card_tables import CardTablesHandler
from widgets.frames.app_frame.handlers.child_windows import ChildWindowHandlers
from widgets.frames.app_frame.handlers.data_loading import DataLoadingHandlers
from widgets.frames.app_frame.handlers.deck_content import DeckContentHandlers
from widgets.frames.app_frame.handlers.deck_render import DeckRenderHandlers
from widgets.frames.app_frame.handlers.research import DeckResearchHandlers
from widgets.frames.app_frame.handlers.sideboard_guide_entries import (
    SideboardGuideEntryHandlers,
)
from widgets.frames.app_frame.handlers.sideboard_guide_io import (
    SideboardGuideImportExportHandlers,
)
from widgets.frames.app_frame.handlers.sideboard_guide_persistence import (
    SideboardGuidePersistenceHandlers,
)
from widgets.frames.app_frame.handlers.sideboard_guide_record import (
    SideboardGuideRecordHandlers,
)
from widgets.frames.app_frame.handlers.toolbar_menu import ToolbarMenuHandlers
from widgets.frames.app_frame.handlers.window_layout import WindowLayoutHandlers

__all__ = [
    "AppFrameHandlersMixin",
    "CardTablesHandler",
    "ChildWindowHandlers",
    "DataLoadingHandlers",
    "DeckContentHandlers",
    "DeckRenderHandlers",
    "DeckResearchHandlers",
    "SideboardGuideEntryHandlers",
    "SideboardGuideImportExportHandlers",
    "SideboardGuidePersistenceHandlers",
    "SideboardGuideRecordHandlers",
    "ToolbarMenuHandlers",
    "WindowLayoutHandlers",
]
