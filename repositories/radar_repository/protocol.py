"""Shared ``self`` contract that the :class:`RadarRepository` mixins assume."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol


class RadarRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``RadarRepository``."""

    db_path: Path

    def _connect(self) -> sqlite3.Connection: ...
