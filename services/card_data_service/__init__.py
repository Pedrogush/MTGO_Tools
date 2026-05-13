"""Card Data Service package - downloads and queries the MTGJSON AtomicCards dataset.

Split by responsibility into internal modules:

- ``schemas``: ``CardEntry`` (msgspec.Struct, dict-compatible) and ``CardIndex``
- ``remote``: HTTP fetch for the MTGJSON dataset (HEAD + GET)
- ``builder``: pure normalization of raw MTGJSON dicts into index entries
- ``storage``: on-disk index/meta paths, msgspec decoder, atomic writes
- ``service``: ``CardDataManager`` orchestrator + ``load_card_manager`` factory
"""

from __future__ import annotations

from services.card_data_service.protocol import CardDataManagerProto
from services.card_data_service.schemas import CardEntry, CardIndex
from services.card_data_service.service import CardDataManager, load_card_manager

__all__ = [
    "CardDataManager",
    "CardDataManagerProto",
    "CardEntry",
    "CardIndex",
    "load_card_manager",
]
