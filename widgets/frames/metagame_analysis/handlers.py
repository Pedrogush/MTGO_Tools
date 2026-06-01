"""Composed event/worker/render mixin for the metagame analysis viewer.

The implementation is split across three low-coupling clusters:

- :mod:`navigation` -> :class:`MetagameNavigationMixin` (toolbar callbacks, control sync)
- :mod:`data_loader` -> :class:`MetagameDataLoaderMixin` (worker thread, population)
- :mod:`visualization` -> :class:`MetagameVisualizationMixin` (pie chart, changes panel)
"""

from __future__ import annotations

from widgets.frames.metagame_analysis.data_loader import MetagameDataLoaderMixin
from widgets.frames.metagame_analysis.navigation import MetagameNavigationMixin
from widgets.frames.metagame_analysis.visualization import MetagameVisualizationMixin


class MetagameAnalysisHandlersMixin(
    MetagameNavigationMixin,
    MetagameDataLoaderMixin,
    MetagameVisualizationMixin,
):
    """Callbacks, data workers, and UI-mutation helpers for :class:`MetagameAnalysisFrame`."""
