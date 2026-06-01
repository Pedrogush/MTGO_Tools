"""Handler mixins composed into :class:`AppFrame`."""

from widgets.frames.app_frame.handlers.app_frame import AppFrameHandlersMixin
from widgets.frames.app_frame.handlers.card_tables import CardTablesHandler
from widgets.frames.app_frame.handlers.child_windows import ChildWindowHandlers
from widgets.frames.app_frame.handlers.data_loading import DataLoadingHandlers
from widgets.frames.app_frame.handlers.deck_content import DeckContentHandlers
from widgets.frames.app_frame.handlers.research import DeckResearchHandlers
from widgets.frames.app_frame.handlers.sideboard_guide import SideboardGuideHandlers

__all__ = [
    "AppFrameHandlersMixin",
    "CardTablesHandler",
    "ChildWindowHandlers",
    "DataLoadingHandlers",
    "DeckContentHandlers",
    "DeckResearchHandlers",
    "SideboardGuideHandlers",
]
