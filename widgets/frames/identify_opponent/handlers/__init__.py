"""Event handlers, background workers, persistence, and window-placement logic
for the opponent tracker.

All ``_on_*`` callbacks, the polling/radar worker threads, cache/config
read-write helpers, and lifecycle hooks live here.  The legacy-path constants
and ``get_latest_deck`` helper are imported from :mod:`..properties`.

The single :class:`MTGOpponentDeckSpyHandlersMixin` is composed from one mixin
per subsystem (calculator, radar, polling, manual archetype, persistence,
window placement, lifecycle).  It remains importable from
``widgets.frames.identify_opponent.handlers`` to preserve existing import sites.
"""

from __future__ import annotations

from widgets.frames.identify_opponent.handlers.archetype import ManualArchetypeMixin
from widgets.frames.identify_opponent.handlers.calculator import CalculatorMixin
from widgets.frames.identify_opponent.handlers.lifecycle import LifecycleMixin
from widgets.frames.identify_opponent.handlers.persistence import PersistenceMixin
from widgets.frames.identify_opponent.handlers.polling import OpponentPollingMixin
from widgets.frames.identify_opponent.handlers.radar import RadarMixin
from widgets.frames.identify_opponent.handlers.window_placement import WindowPlacementMixin


class MTGOpponentDeckSpyHandlersMixin(
    CalculatorMixin,
    RadarMixin,
    OpponentPollingMixin,
    ManualArchetypeMixin,
    PersistenceMixin,
    WindowPlacementMixin,
    LifecycleMixin,
):
    """Callbacks, workers, persistence, and window-placement for the tracker frame."""


__all__ = [
    "MTGOpponentDeckSpyHandlersMixin",
    "CalculatorMixin",
    "RadarMixin",
    "OpponentPollingMixin",
    "ManualArchetypeMixin",
    "PersistenceMixin",
    "WindowPlacementMixin",
    "LifecycleMixin",
]
