"""wxPython MTGO opponent tracker overlay package.

Re-exports :class:`MTGOpponentDeckSpy`, :class:`_LoadArchetypeDialog`, and
:func:`main` for external callers (including the ``mtgo-opponent-tracker``
console-script entry point declared in ``pyproject.toml``).

The legacy-path constants, ``get_latest_deck``, ``wx``, and
``find_archetype_by_name`` are surfaced at package scope so the UI test harness
in ``tests/ui/conftest.py`` and ``tests/test_identify_opponent_radar.py`` can
continue to ``monkeypatch.setattr(identify_opponent, ...)`` and
``patch("widgets.frames.identify_opponent.<name>")`` exactly as before.
"""

from __future__ import annotations

import wx  # noqa: F401 - re-exported for tests that patch identify_opponent.wx

from utils.archetype_resolver import (
    find_archetype_by_name,  # noqa: F401 - re-exported for tests that patch this name
)
from widgets.frames.identify_opponent.frame import (
    MTGOpponentDeckSpy,
    _LoadArchetypeDialog,
    main,
)
from widgets.frames.identify_opponent.properties import (
    LEGACY_DECK_MONITOR_CACHE,
    LEGACY_DECK_MONITOR_CACHE_CONFIG,
    LEGACY_DECK_MONITOR_CONFIG,
    get_latest_deck,
)

__all__ = [
    "LEGACY_DECK_MONITOR_CACHE",
    "LEGACY_DECK_MONITOR_CACHE_CONFIG",
    "LEGACY_DECK_MONITOR_CONFIG",
    "MTGOpponentDeckSpy",
    "_LoadArchetypeDialog",
    "get_latest_deck",
    "main",
]
