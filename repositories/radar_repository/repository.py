"""RadarRepository composed from responsibility-specific mixins."""

from __future__ import annotations

from pathlib import Path

from repositories.radar_repository.reads import ReadsMixin
from repositories.radar_repository.schema import SchemaMixin
from repositories.radar_repository.writes import WritesMixin
from utils.constants import RADAR_CACHE_DB_FILE


class RadarRepository(
    SchemaMixin,
    WritesMixin,
    ReadsMixin,
):
    """Read and write locally cached precomputed radar snapshots."""

    def __init__(self, db_path: Path = RADAR_CACHE_DB_FILE) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
