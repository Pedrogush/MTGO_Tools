"""Handler mixins composed into :class:`AppFrame`."""

from widgets.frames.app_frame.handlers.app_frame import AppFrameHandlersMixin
from widgets.frames.app_frame.handlers.card_inspector_preview import (
    CardInspectorPreviewHandlers,
)
from widgets.frames.app_frame.handlers.card_selection import CardSelectionHandlers
from widgets.frames.app_frame.handlers.card_shortcuts import CardShortcutHandlers
from widgets.frames.app_frame.handlers.child_windows import ChildWindowHandlers
from widgets.frames.app_frame.handlers.data_loading import DataLoadingHandlers
from widgets.frames.app_frame.handlers.deck_content import DeckContentHandlers
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
from widgets.frames.app_frame.handlers.zone_editing import ZoneEditingHandlers

__all__ = [
    "AppFrameHandlersMixin",
    "CardInspectorPreviewHandlers",
    "CardSelectionHandlers",
    "CardShortcutHandlers",
    "ChildWindowHandlers",
    "DataLoadingHandlers",
    "DeckContentHandlers",
    "DeckResearchHandlers",
    "SideboardGuideEntryHandlers",
    "SideboardGuideImportExportHandlers",
    "SideboardGuidePersistenceHandlers",
    "SideboardGuideRecordHandlers",
    "ZoneEditingHandlers",
]
