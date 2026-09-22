"""Where a deck's git repo lives on disk, and how it is opened.

One repo per deck, under ``<DECK_HISTORY_DIR>/<deck_key>/``. It is a mirror:
the user's real decklist stays a plain ``.txt`` in their deck folder
(``DECKS_DIR``) and never gains a ``.git`` neighbour, because those files are
flat and share one directory -- there is no per-deck directory there to root a
repo in, and putting version metadata beside them would change what the user's
deck folder is.

That argument rules out the deck folder; it says nothing about which *other*
directory to use, and the first answer -- ``cache/deck_vcs/``, chosen because
that is where this repo already keys per-deck notes, outboard and sideboard
guides (:mod:`repositories.deck_repository.metadata_store`) -- was wrong.
Everything else under ``cache/`` can be refetched or recomputed, which is why
the uninstaller and ``scripts/clear_caches.py`` both sweep the whole directory
while promising that what the user made is kept. A deck's edit history is the
user's own work and nothing can rebuild it, so it lives in its own top-level
directory beside ``config/`` that neither sweep touches. Unlike the notes
stores, it is also a directory tree of open-able git repos rather than one
JSON file, so nothing is lost by not sharing their home.

Handles are opened per operation, and a caller that is about to do a *batch* of
reads wraps them in :meth:`StoreMixin.read_session` to share one. Opening is not
free: :class:`~dulwich.repo.Repo` re-reads ``.git/config`` and rescans the pack
directory every time, which measured at roughly 2 ms per open. Building the
graph for a 100-version deck opened the repo 200 times -- twice per commit --
and spent 98% of its time on that rather than on any comparison.

A session is **read-only and short-lived by contract**. It holds the handle open
and memoizes the decklist blob behind each sha, so a walk that wants every
commit's text and its parent's reads each blob once instead of twice. Nothing
inside a session may write, because a commit made through another handle would
leave the session's view of the object store behind. Sessions are thread-local:
this repository is a process-wide singleton, and the graph is built on a
background thread while the UI thread may be reading the same deck.

An open handle keeps packfile handles that would stop the cache directory being
cleaned up on Windows, which is why a session is scoped to one operation rather
than held for the life of the app.
"""

from __future__ import annotations

import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
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


@dataclass
class _ReadSession:
    """One open handle, and the blobs read through it, for a batch of reads."""

    repo: Repo
    #: Re-entrancy count, so a session may be opened inside another.
    depth: int = 1
    #: Decklist text by commit sha, memoized for this session only.
    blobs: dict[str, str] = field(default_factory=dict)


#: Active read sessions for the calling thread, keyed by repo path.
_sessions = threading.local()


def _session_map() -> dict[str, _ReadSession]:
    active = getattr(_sessions, "by_path", None)
    if active is None:
        active = {}
        _sessions.by_path = active
    return active


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

    def adopt_legacy_repo(self, deck_key: str, legacy_key: str) -> bool:
        """Move a repo left under the old cache root onto ``deck_key``; did it?

        Deck history never shipped -- it exists only on ``develop`` -- so there
        is no installed build whose histories need migrating. What does exist is
        a developer checkout holding repos under ``cache/deck_vcs/<name>/`` from
        before the root moved and before a deck was keyed by anything but its
        name, and throwing those away for no reason would be rude.

        Deliberately not a migration pass over the whole old root: the old key
        was a *name*, and only a caller holding the deck record knows which name
        a given deck used to answer to. This adopts one deck, when that caller
        asks, and only into a key that has no repo yet -- so it can never
        overwrite a history the new layout already has, and running twice is a
        no-op. A caller whose legacy key came from a shared fallback rather than
        the deck's own name must not ask; see
        :func:`services.deck_vcs_service.legacy_deck_key_for`.
        """
        if not legacy_key or self.has_repo(deck_key):
            return False
        safe_legacy = sanitize_filename(legacy_key, fallback="manual").lower()
        source = self._legacy_root / safe_legacy
        if not (source / ".git").exists():
            return False
        target = self.repo_path(deck_key)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(source), str(target))
        except OSError as exc:
            logger.warning(f"Could not adopt legacy deck history {source}: {exc}")
            return False
        logger.info(f"Adopted legacy deck history {source} as {target}")
        return True

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
        """Open ``deck_key``'s repo for the duration of one operation.

        Inside a :meth:`read_session` this yields that session's handle instead
        of opening another. ``create=True`` always takes its own handle: a
        session is read-only, and a write must not reuse a view of the object
        store that predates it.
        """
        from dulwich.repo import Repo

        if not create:
            session = self._active_session(deck_key)
            if session is not None:
                yield session.repo
                return

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

    # ------------------------------------------------------------------ read sessions ------------------------------------------------------------------
    def _active_session(self, deck_key: str) -> _ReadSession | None:
        """This thread's open session for ``deck_key``, if any."""
        active = getattr(_sessions, "by_path", None)
        if not active:
            return None
        return active.get(str(self.repo_path(deck_key)))

    @contextmanager
    def read_session(self, deck_key: str) -> Iterator[None]:
        """Share one open handle, and one blob cache, across a batch of reads.

        Read-only: nothing inside may commit, branch or check out. A deck with
        no repo yet is not an error -- the block runs with no session, and the
        reads inside it fail or come back empty exactly as they would alone.
        """
        path = self.repo_path(deck_key)
        if not (path / ".git").exists():
            yield
            return

        active = _session_map()
        key = str(path)
        existing = active.get(key)
        if existing is not None:
            existing.depth += 1
            try:
                yield
            finally:
                existing.depth -= 1
            return

        from dulwich.repo import Repo

        session = _ReadSession(repo=Repo(key))
        active[key] = session
        try:
            yield
        finally:
            active.pop(key, None)
            session.repo.close()

    def _session_blob(self, deck_key: str, sha: str) -> str | None:
        """A blob this session has already read, or ``None``."""
        session = self._active_session(deck_key)
        return None if session is None else session.blobs.get(sha)

    def _remember_blob(self, deck_key: str, sha: str, text: str) -> None:
        session = self._active_session(deck_key)
        if session is not None:
            session.blobs[sha] = text
