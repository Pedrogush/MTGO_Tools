"""Shared ``self`` contract that the :class:`FormatCardPoolRepository` mixins assume."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol


class FormatCardPoolRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``FormatCardPoolRepository``."""

    db_path: Path

    def _connect(self) -> sqlite3.Connection: ...
