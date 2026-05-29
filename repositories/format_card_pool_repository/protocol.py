"""Shared ``self`` contract that the :class:`FormatCardPoolRepository` mixins assume."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Protocol


class FormatCardPoolRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``FormatCardPoolRepository``."""

    db_path: Path
    _read_lock: threading.RLock
    _summary_cache: dict[str, Any]
    _card_total_cache: dict[tuple[str, str], int | None]

    def _connect(self) -> sqlite3.Connection: ...

    def _read_connection(self) -> sqlite3.Connection: ...

    def _invalidate_read_state(self) -> None: ...
