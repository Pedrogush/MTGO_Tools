"""FormatCardPoolRepository composed from responsibility-specific mixins."""

from __future__ import annotations

from pathlib import Path

from repositories.format_card_pool_repository.reads import ReadsMixin
from repositories.format_card_pool_repository.schema import SchemaMixin
from repositories.format_card_pool_repository.writes import WritesMixin
from utils.constants import FORMAT_CARD_POOL_DB_FILE


class FormatCardPoolRepository(
    SchemaMixin,
    WritesMixin,
    ReadsMixin,
):
    """Read and write locally cached format card-pool snapshots."""

    def __init__(self, db_path: Path = FORMAT_CARD_POOL_DB_FILE) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
