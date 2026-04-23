"""Handler mixins composed into :class:`AppFrame`."""

from widgets.frames.app_frame.handlers.app_events import AppEventHandlers
from widgets.frames.app_frame.handlers.app_frame import AppFrameHandlersMixin
from widgets.frames.app_frame.handlers.card_tables import CardTablesHandler
from widgets.frames.app_frame.handlers.sideboard_guide import SideboardGuideHandlers

__all__ = [
    "AppEventHandlers",
    "AppFrameHandlersMixin",
    "CardTablesHandler",
    "SideboardGuideHandlers",
]
