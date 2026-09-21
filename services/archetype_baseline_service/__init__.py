"""Archetype pool baselines: what an archetype has already decided.

Given a pool of decks sharing an archetype and format, this works out which
cards the archetype always runs (and at what count), which it always runs at a
count that moves, and how many slots are genuinely the player's own. That last
number -- the flex slot count, with the ranked list of cards competing for those
slots -- is the useful output; a single modal decklist hides it.

The computed baseline then becomes the **root commit** of a deck's version
history (:mod:`repositories.deck_vcs_repository.baseline`), so diffing a deck
against its archetype is an ordinary diff against an ancestor.

Split by responsibility:

- ``models``: the plain records the analysis produces
- ``frequency``: the per-card frequency table the whole thing derives from
- ``classify``: staple / partial staple / flex, and the baseline decklist
- ``store``: persisting computed baselines, keyed by archetype and format
- ``service``: pool fetching, orchestration, and root-commit seeding

Nothing in this package imports wx, so the analysis is unit-testable directly.
"""

from __future__ import annotations

from services.archetype_baseline_service.classify import (
    build_baseline,
    classify_card,
)
from services.archetype_baseline_service.frequency import (
    build_frequency_table,
    deck_card_counts,
    pool_zone_sizes,
)
from services.archetype_baseline_service.membership import (
    MEMBERSHIP_THRESHOLD,
    jaccard,
    maindeck_names,
    partition_pool,
    similarity_scores,
)
from services.archetype_baseline_service.models import (
    ArchetypeBaseline,
    BaselineCard,
    CardFrequency,
    CardRole,
    ExcludedDeck,
    FlexCandidate,
    PoolMembership,
    ZoneShape,
)
from services.archetype_baseline_service.service import (
    MIN_POOL_SIZE,
    ArchetypeBaselineService,
    get_archetype_baseline_service,
    reset_archetype_baseline_service,
)
from services.archetype_baseline_service.store import BaselineStore, baseline_key

__all__ = [
    "MEMBERSHIP_THRESHOLD",
    "MIN_POOL_SIZE",
    "ArchetypeBaseline",
    "ArchetypeBaselineService",
    "BaselineCard",
    "BaselineStore",
    "CardFrequency",
    "CardRole",
    "ExcludedDeck",
    "FlexCandidate",
    "PoolMembership",
    "ZoneShape",
    "baseline_key",
    "build_baseline",
    "build_frequency_table",
    "classify_card",
    "deck_card_counts",
    "get_archetype_baseline_service",
    "jaccard",
    "maindeck_names",
    "partition_pool",
    "pool_zone_sizes",
    "reset_archetype_baseline_service",
    "similarity_scores",
]
