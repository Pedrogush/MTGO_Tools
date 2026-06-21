"""Event handlers, workers, and UI populators for the card inspector panel.

The single :class:`CardInspectorPanelHandlersMixin` is composed from one mixin
per topic (content population + wiring, printing navigation, async image
pipeline).  It remains importable from
``widgets.panels.card_inspector_panel.handlers`` to preserve existing import
sites (``frame.py``).
"""

from __future__ import annotations

from widgets.panels.card_inspector_panel.handlers.content import ContentMixin
from widgets.panels.card_inspector_panel.handlers.image_pipeline import ImagePipelineMixin
from widgets.panels.card_inspector_panel.handlers.printing_nav import PrintingNavMixin


class CardInspectorPanelHandlersMixin(
    ContentMixin,
    PrintingNavMixin,
    ImagePipelineMixin,
):
    """Event callbacks, public state setters, workers, and UI populators for
    :class:`CardInspectorPanel`.
    """


__all__ = [
    "CardInspectorPanelHandlersMixin",
    "ContentMixin",
    "PrintingNavMixin",
    "ImagePipelineMixin",
]
