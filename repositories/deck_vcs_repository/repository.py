"""DeckVcsRepository composed from responsibility-specific mixins."""

from __future__ import annotations

from pathlib import Path

from repositories.deck_vcs_repository.branches import BranchesMixin
from repositories.deck_vcs_repository.commits import CommitsMixin
from repositories.deck_vcs_repository.diffs import DiffsMixin
from repositories.deck_vcs_repository.store import StoreMixin


class DeckVcsRepository(
    StoreMixin,
    CommitsMixin,
    BranchesMixin,
    DiffsMixin,
):
    """Git-backed version history for saved decks, one repo per deck."""

    def __init__(self, vcs_root: Path | None = None):
        if vcs_root is None:
            from utils.constants import CACHE_DIR

            vcs_root = Path(CACHE_DIR) / "deck_vcs"
        self._vcs_root = Path(vcs_root)
