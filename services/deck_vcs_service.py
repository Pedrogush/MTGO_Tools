"""Deck version control, as the rest of the app uses it.

The repository layer (:mod:`repositories.deck_vcs_repository`) owns git. This
owns the *decisions* around it: what a save is called in the history, when an
externally edited file counts as a version already held, and which file on disk
a checkout is allowed to rewrite.

The last of those is the constraint the whole feature lives under. The user's
decklist is a plain ``.txt`` that MTGO and Manatraders import, so no version
metadata may ever enter it. A checkout therefore writes exactly the decklist and
nothing else, and the git side of it stays in the mirror under ``cache/``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from repositories.deck_vcs_repository import DeckCommit, DeckDiff
from repositories.deck_vcs_repository.normalize import normalize_decklist
from utils.atomic_io import atomic_write_text

if TYPE_CHECKING:
    from repositories.deck_vcs_repository import DeckVcsRepository


def deck_key_for(deck: dict | None, file_path: Path | None) -> str:
    """The history key for a deck, agreed on by every caller.

    A deck that lives in a file is keyed by that file's stem, because the file
    is the thing the user keeps and comes back to -- two sessions that open
    ``Mono Red.txt`` must land on the same history. Only a deck with no file
    behind it (a scraped list, an average) falls back to its record's ``href``,
    which is what :meth:`DeckRepository.get_current_deck_key` uses throughout
    the rest of the app.
    """
    from utils.deck import sanitize_filename

    if file_path is not None:
        return sanitize_filename(Path(file_path).stem, fallback="manual").lower()
    if deck:
        return str(deck.get("href") or deck.get("name", "manual")).lower()
    return "manual"


class ExternalEditStatus(Enum):
    """What a ``.txt`` loaded from disk turned out to be."""

    #: The deck has no version history yet.
    NO_HISTORY = "no_history"
    #: Its content matches a commit already in the history.
    KNOWN = "known"
    #: It is a decklist this history has never seen -- the user edited the file
    #: outside the app. The caller must ask what to do; guessing would either
    #: invent a commit the user did not ask for or silently drop their edit.
    UNATTRIBUTED = "unattributed"


@dataclass(frozen=True)
class ExternalEdit:
    """The verdict on an externally loaded decklist."""

    status: ExternalEditStatus
    sha: str | None = None


@dataclass(frozen=True)
class GraphCommit:
    """A commit plus the presentation facts the graph view needs."""

    commit: DeckCommit
    #: Change against this commit's parent, already summarized for a node label.
    diff: DeckDiff

    @property
    def sha(self) -> str:
        return self.commit.sha

    @property
    def short_sha(self) -> str:
        return self.commit.short_sha

    @property
    def label(self) -> str:
        """What the node reads as: the message, else the diff, else the sha."""
        return self.commit.message or self.diff.summary() or self.commit.short_sha


class DeckVcsService:
    """Version-control operations for decks, decoupled from wx UI."""

    def __init__(self, *, vcs_repo: DeckVcsRepository | None = None) -> None:
        if vcs_repo is None:
            from repositories.deck_vcs_repository import get_deck_vcs_repository

            vcs_repo = get_deck_vcs_repository()
        self.vcs_repo = vcs_repo

    # ------------------------------------------------------------------ saving ------------------------------------------------------------------
    def record_save(
        self, deck_key: str, deck_text: str, *, message: str | None = None
    ) -> str | None:
        """Commit ``deck_text`` as the next version of ``deck_key``.

        Returns the new sha, or ``None`` when the deck is unchanged -- saving a
        list whose cards are identical to the current tip must not litter the
        history with empty commits, and since every write is normalized first, a
        pure reordering counts as unchanged.
        """
        if not deck_text.strip():
            return None

        tip_text = self.current_version_text(deck_key)
        if tip_text is not None and normalize_decklist(tip_text) == normalize_decklist(deck_text):
            logger.debug(f"Deck unchanged, no version recorded: {deck_key}")
            return None

        resolved = message or self.describe_change(deck_key, deck_text)
        return self.vcs_repo.commit_deck(deck_key, deck_text, resolved)

    def describe_change(self, deck_key: str, deck_text: str) -> str:
        """An auto-summary of ``deck_text`` against the current tip.

        This is what makes a graph readable without the user having typed a
        commit message for every save -- the node says "+2 Fable, -2 Consider"
        rather than "save 14".
        """
        tip_text = self.current_version_text(deck_key)
        if tip_text is None:
            return "Initial version"
        from repositories.deck_vcs_repository.diffs import diff_decklists

        summary = diff_decklists(tip_text, deck_text).summary()
        return summary or "No card changes"

    # ------------------------------------------------------------------ reading ------------------------------------------------------------------
    def has_history(self, deck_key: str) -> bool:
        return self.vcs_repo.has_repo(deck_key)

    def current_branch(self, deck_key: str) -> str | None:
        return self.vcs_repo.current_branch(deck_key)

    def list_branches(self, deck_key: str) -> list[str]:
        return self.vcs_repo.list_branches(deck_key)

    def current_version_text(self, deck_key: str) -> str | None:
        """The decklist at the current ``HEAD``, or ``None`` with no history."""
        commits = self.vcs_repo.list_commits(deck_key)
        head = next((c for c in commits if c.is_head), None)
        if head is None:
            return None
        return self.vcs_repo.read_commit_text(deck_key, head.sha)

    def version_text(self, deck_key: str, sha: str) -> str:
        """The decklist stored in one version. Never touches the user's file."""
        return self.vcs_repo.read_commit_text(deck_key, sha)

    def build_graph(self, deck_key: str) -> list[GraphCommit]:
        """Every version of the deck, newest first, with its change summary."""
        graph: list[GraphCommit] = []
        for commit in self.vcs_repo.list_commits(deck_key):
            parent = commit.parents[0] if commit.parents else None
            graph.append(
                GraphCommit(
                    commit=commit,
                    diff=self.vcs_repo.diff_from_parent(deck_key, commit.sha, parent),
                )
            )
        return graph

    def diff(self, deck_key: str, base_sha: str, target_sha: str) -> DeckDiff:
        return self.vcs_repo.diff_commits(deck_key, base_sha, target_sha)

    def unified_diff(self, deck_key: str, base_sha: str, target_sha: str) -> list[str]:
        return self.vcs_repo.unified_diff(deck_key, base_sha, target_sha)

    # ------------------------------------------------------------------ moving ------------------------------------------------------------------
    def create_branch(self, deck_key: str, name: str, at_sha: str) -> str:
        return self.vcs_repo.create_branch(deck_key, name, at_sha)

    def checkout(
        self, deck_key: str, sha: str, *, deck_file: Path | None = None
    ) -> tuple[str, str]:
        """Move onto version ``sha`` and rewrite the user's decklist file.

        Returns ``(branch_name, decklist_text)``. ``deck_file`` is the user's own
        ``.txt``; it receives the decklist and nothing else. Checking out a
        commit that is not a branch tip creates a branch there first, so no
        version the user makes next can end up unreachable.
        """
        branch, text = self.vcs_repo.checkout(deck_key, sha)
        self._write_user_file(deck_file, text)
        return branch, text

    def switch_branch(self, deck_key: str, name: str, *, deck_file: Path | None = None) -> str:
        """Move onto branch ``name`` and rewrite the user's decklist file."""
        text = self.vcs_repo.switch_branch(deck_key, name)
        self._write_user_file(deck_file, text)
        return text

    @staticmethod
    def _write_user_file(deck_file: Path | None, text: str) -> None:
        if deck_file is None:
            return
        # Normalized, like every other write path: the file the user keeps and
        # the blob in the history are the same bytes, which is what lets the
        # next load recognise the file as a version it already holds.
        atomic_write_text(Path(deck_file), normalize_decklist(text))
        logger.info(f"Deck file rewritten from version history: {deck_file}")

    # ------------------------------------------------------------------ identity ------------------------------------------------------------------
    def identify(self, deck_key: str, deck_text: str) -> ExternalEdit:
        """Decide what a decklist loaded from disk is, relative to the history.

        The file carries no version metadata by design, so content is the only
        handle there is.
        """
        if not self.vcs_repo.has_repo(deck_key):
            return ExternalEdit(status=ExternalEditStatus.NO_HISTORY)
        sha = self.vcs_repo.find_commit_by_text(deck_key, deck_text)
        if sha is not None:
            return ExternalEdit(status=ExternalEditStatus.KNOWN, sha=sha)
        return ExternalEdit(status=ExternalEditStatus.UNATTRIBUTED)

    def attach_unattributed(
        self, deck_key: str, deck_text: str, *, as_branch: str | None = None
    ) -> str:
        """Record an externally edited decklist as a version.

        ``as_branch`` starts a new branch at the current tip and commits there;
        without it the commit extends the current branch. Either way the commit
        is reachable from a ref the moment it exists.
        """
        if as_branch:
            commits = self.vcs_repo.list_commits(deck_key)
            head = next((c for c in commits if c.is_head), None)
            if head is not None:
                created = self.vcs_repo.create_branch(deck_key, as_branch, head.sha)
                self.vcs_repo.switch_branch(deck_key, created)
        return self.vcs_repo.commit_deck(deck_key, deck_text, "Edited outside the app")


_default_service: DeckVcsService | None = None


def get_deck_vcs_service() -> DeckVcsService:
    global _default_service
    if _default_service is None:
        _default_service = DeckVcsService()
    return _default_service


def reset_deck_vcs_service() -> None:
    """Reset the global deck-VCS service (use in tests for isolation)."""
    global _default_service
    _default_service = None
