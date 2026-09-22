"""Writing a version and reading one back.

Every write goes through :func:`~repositories.deck_vcs_repository.normalize.normalize_decklist`
before it reaches the index -- that is the invariant the diff quality rests on,
and it is enforced here rather than trusted to callers, because this mixin is the
only place in the app that writes into a deck repo.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

from loguru import logger

from repositories.deck_vcs_repository.baseline import BASELINE_IDENTITY
from repositories.deck_vcs_repository.models import DeckCommit
from repositories.deck_vcs_repository.normalize import decklist_fingerprint, normalize_decklist
from repositories.deck_vcs_repository.store import COMMITTER, DECK_FILENAME
from utils.atomic_io import atomic_write_text

if TYPE_CHECKING:
    from repositories.deck_vcs_repository.protocol import DeckVcsRepositoryProto

    _Base = DeckVcsRepositoryProto
else:
    _Base = object


class CommitsMixin(_Base):
    """Commit a decklist, read one back, and walk a deck's history."""

    def commit_deck(self, deck_key: str, deck_text: str, message: str) -> str:
        """Commit ``deck_text`` onto whatever branch ``HEAD`` points at.

        Returns the new commit's sha. The text is normalized first, so a save
        that only reordered cards produces no new commit content and the caller
        can tell it was a no-op by comparing against the previous tip.
        """
        from dulwich import porcelain

        normalized = normalize_decklist(deck_text)
        with self._open(deck_key, create=True) as repo:
            deck_file = self._deck_file(deck_key)
            atomic_write_text(deck_file, normalized)
            porcelain.add(repo.path, paths=[str(deck_file)])
            sha = porcelain.commit(
                repo.path,
                message=message.encode("utf-8"),
                committer=COMMITTER,
                author=COMMITTER,
            )
        resolved = sha.decode("ascii") if isinstance(sha, bytes) else str(sha)
        logger.info(f"Deck version committed: {deck_key} {resolved[:7]} ({message})")
        return resolved

    def read_commit_text(self, deck_key: str, sha: str) -> str:
        """The decklist stored in commit ``sha``.

        Reads the blob straight out of the object store, so previewing a version
        never touches the working tree -- looking at a node in the graph must not
        be a checkout.

        Inside a :meth:`~repositories.deck_vcs_repository.store.StoreMixin.read_session`
        the text is memoized, which is what stops a history walk reading every
        blob twice: each commit is both its own "after" and the next one's
        "before".
        """
        cached = self._session_blob(deck_key, sha)
        if cached is not None:
            return cached
        with self._open(deck_key) as repo:
            text = _blob_text(repo, sha)
        self._remember_blob(deck_key, sha, text)
        return text

    def commit_fingerprint(self, deck_key: str, sha: str) -> str:
        return decklist_fingerprint(self.read_commit_text(deck_key, sha))

    def find_commit_by_text(self, deck_key: str, deck_text: str) -> str | None:
        """The sha of a commit holding ``deck_text``'s canonical form, if any.

        This is what makes an externally edited ``.txt`` identifiable: the file
        carries no version metadata by design, so content is the only handle on
        "is this a version I already have?".
        """
        if not self.has_repo(deck_key):
            return None
        target = decklist_fingerprint(deck_text)
        # One handle for the whole scan: this reads a blob per commit, and
        # re-opening the repo for each one is what made loading a deck with a
        # long history stall.
        with self.read_session(deck_key):
            for commit in self.iter_commits(deck_key):
                if decklist_fingerprint(self.read_commit_text(deck_key, commit.sha)) == target:
                    return commit.sha
        return None

    def iter_commits(self, deck_key: str) -> Iterator[DeckCommit]:
        """Every commit in the deck's history, newest first.

        The walk includes all branch tips, not just ``HEAD``, because the graph
        view has to show branches the user is not currently on -- that is the
        whole point of it.
        """
        if not self.has_repo(deck_key):
            return
        with self._open(deck_key) as repo:
            tips_by_sha: dict[str, list[str]] = {}
            refs = repo.refs.as_dict()
            for ref, sha in refs.items():
                if ref.startswith(b"refs/heads/"):
                    name = ref[len(b"refs/heads/") :].decode("utf-8")
                    tips_by_sha.setdefault(sha.decode("ascii"), []).append(name)

            head_sha = _head_sha(repo)
            include = [sha for ref, sha in refs.items() if ref.startswith(b"refs/heads/")]
            if not include:
                return
            for entry in repo.get_walker(include=include):
                commit = entry.commit
                sha = commit.id.decode("ascii")
                yield DeckCommit(
                    sha=sha,
                    parents=tuple(p.decode("ascii") for p in commit.parents),
                    message=commit.message.decode("utf-8", errors="replace").strip(),
                    timestamp=int(commit.commit_time),
                    branches=tuple(sorted(tips_by_sha.get(sha, ()))),
                    is_head=sha == head_sha,
                    is_baseline=bytes(commit.author) == BASELINE_IDENTITY,
                )

    def list_commits(self, deck_key: str) -> list[DeckCommit]:
        return list(self.iter_commits(deck_key))

    def head_sha(self, deck_key: str) -> str | None:
        """What ``HEAD`` points at, without walking the history to find it.

        ``list_commits`` decodes every commit object in the deck's history; a
        caller that only wants the current tip -- the unchanged check on a save,
        for one -- was paying for the whole walk to read one ref.
        """
        if not self.has_repo(deck_key):
            return None
        with self._open(deck_key) as repo:
            return _head_sha(repo)


def _blob_text(repo: Any, sha: str) -> str:
    commit = repo[sha.encode("ascii") if isinstance(sha, str) else sha]
    tree = repo[commit.tree]
    _mode, blob_sha = tree[DECK_FILENAME.encode("ascii")]
    return str(repo[blob_sha].data.decode("utf-8"))


def _head_sha(repo: Any) -> str | None:
    try:
        return str(repo.refs[b"HEAD"].decode("ascii"))
    except KeyError:
        return None
