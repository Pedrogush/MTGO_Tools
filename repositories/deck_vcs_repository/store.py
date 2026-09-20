"""Where a deck's git repo lives on disk, and how it is opened.

One repo per deck, under ``<CACHE_DIR>/deck_vcs/<deck_key>/``. It is a mirror:
the user's real decklist stays a plain ``.txt`` in their deck folder
(``DECKS_DIR``) and never gains a ``.git`` neighbour, because those files are
flat and share one directory -- there is no per-deck directory there to root a
repo in, and putting version metadata beside them would change what the user's
deck folder is. Keying per-deck state into ``cache/`` instead is what this repo
already does for notes, outboard and sideboard guides
(:mod:`repositories.deck_repository.metadata_store`).

Handles are opened per operation rather than cached. A deck's history is a
handful of tiny objects, so there is nothing to gain by holding one, and an open
:class:`~dulwich.repo.Repo` keeps packfile handles that would stop the cache
directory being cleaned up on Windows.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from utils.deck import sanitize_filename

if TYPE_CHECKING:
    from dulwich.repo import Repo

    from repositories.deck_vcs_repository.protocol import DeckVcsRepositoryProto

    _Base = DeckVcsRepositoryProto
else:
    _Base = object

#: The single tracked file inside every deck repo.
DECK_FILENAME = "deck.txt"

#: Deck repos are written by the app, never by a person, so the identity is the
#: app's rather than the user's -- nothing here is pushed anywhere.
COMMITTER = b"MTGO Tools <mtgo-tools@localhost>"

#: The branch a new deck repo starts on. dulwich still inits to ``master``; this
#: is set explicitly so branch names shown in the graph do not depend on which
#: dulwich version is installed.
DEFAULT_BRANCH = "main"


class StoreMixin(_Base):
    """Repo path resolution, creation, and scoped open handles."""

    def repo_path(self, deck_key: str) -> Path:
        """The directory holding ``deck_key``'s repo.

        ``deck_key`` comes from a deck record's ``href`` (see
        ``DeckRepository.get_current_deck_key``), which for a scraped deck is a
        URL fragment containing slashes -- so it is sanitized into a single path
        segment rather than trusted as one.
        """
        safe = sanitize_filename(deck_key, fallback="manual").lower()
        return self._vcs_root / safe

    def _deck_file(self, deck_key: str) -> Path:
        return self.repo_path(deck_key) / DECK_FILENAME

    def has_repo(self, deck_key: str) -> bool:
        return (self.repo_path(deck_key) / ".git").exists()

    def create_repo(self, deck_key: str) -> Path:
        """Create ``deck_key``'s repo if it does not exist; return its path."""
        from dulwich import porcelain

        path = self.repo_path(deck_key)
        if (path / ".git").exists():
            return path
        path.mkdir(parents=True, exist_ok=True)
        repo = porcelain.init(str(path))
        try:
            # Point HEAD at an unborn ``main`` before the first commit, which is
            # what makes that commit land there instead of on dulwich's default.
            repo.refs.set_symbolic_ref(b"HEAD", f"refs/heads/{DEFAULT_BRANCH}".encode("ascii"))
        finally:
            repo.close()
        logger.info(f"Created deck version repo: {path}")
        return path

    @contextmanager
    def _open(self, deck_key: str, *, create: bool = False) -> Iterator[Repo]:
        """Open ``deck_key``'s repo for the duration of one operation."""
        from dulwich.repo import Repo

        if create:
            self.create_repo(deck_key)
        path = self.repo_path(deck_key)
        if not (path / ".git").exists():
            raise FileNotFoundError(f"No deck version history for {deck_key!r}")
        repo = Repo(str(path))
        try:
            yield repo
        finally:
            repo.close()
