"""Public setters for the loading splash frame."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from widgets.frames.splash_frame.protocol import LoadingFrameProto

    _Base = LoadingFrameProto
else:
    _Base = object


class LoadingFramePropertiesMixin(_Base):
    """Public state accessors for :class:`LoadingFrame`.

    Kept as a mixin (no ``__init__``) so :class:`LoadingFrame` remains the
    single source of truth for instance-state initialization.
    """

    def set_ready(self, on_ready: Callable[[], None] | None = None) -> None:
        self._ready = True
        self._on_ready = on_ready
        self._maybe_finish()
