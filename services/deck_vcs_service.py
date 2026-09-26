"""Deck version control, as the rest of the app uses it.

The repository layer (:mod:`repositories.deck_vcs_repository`) owns git. This
owns the *decisions* around it: what a save is called in the history, when an
externally edited file counts as a version already held, and which file on disk
a checkout is allowed to rewrite.

The last of those is the constraint the whole feature lives under. The user's
decklist is a plain ``.txt`` that MTGO and Manatraders import, so no version
metadata may ever enter it. A checkout therefore writes exactly the decklist and
nothing else, and the git side of it stays in the mirror under
``DECK_HISTORY_DIR``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from repositories.deck_vcs_repository import CardDelta, DeckCommit, DeckDiff
from repositories.deck_vcs_repository.normalize import normalize_decklist
from utils.atomic_io import atomic_write_text

if TYPE_CHECKING:
    from repositories.deck_vcs_repository import DeckVcsRepository


def deck_key_for(deck: dict | None, file_path: Path | None) -> str:
    """The history key for a deck, agreed on by every caller.

    The deck's **stable id** decides this, and nothing else does. The id is
    stamped on the record the first time the deck is saved and never changes
    again, so a rename keeps the whole version graph and two decks that happen
    to share a name keep two histories -- see :mod:`services.deck_identity` for
    why the name could not go on doing this job.

    A deck that has never been saved has no id yet, and falls back to
    :func:`legacy_deck_key_for` -- the name-shaped key this used to return. That
    deck has no history to find either, so the fallback only has to be stable
    for the length of a session; what it is really for is reading a history
    written by a build that predates the id, which the first save then adopts
    onto the id (:meth:`DeckVcsRepository.adopt_legacy_repo`).
    """
    from services.deck_identity import deck_id_of

    deck_id = deck_id_of(deck)
    if deck_id:
        return deck_id
    return legacy_deck_key_for(deck, file_path)


def adoptable_legacy_key(deck: dict | None, file_path: Path | None) -> str:
    """The old name-shaped key, but only when it named *this* deck alone.

    A repo under the old key may be adopted onto a deck's id, which moves one
    user's history onto the deck it belongs to. That is only safe for a key
    derived from the deck's own name or its own file: the remaining fallbacks
    are shared -- a scraped deck's ``href`` is an archetype slug every deck of
    that archetype answers to, and ``"manual"`` is every unnamed, file-less
    deck there has ever been -- so adopting one of those would hand a deck a
    history some other deck wrote. Returns ``""`` for those.
    """
    from services.deck_name import deck_name_of
    from utils.deck import sanitize_filename

    name = deck_name_of(deck)
    if name:
        return sanitize_filename(name, fallback="manual").lower()
    if file_path is not None:
        return sanitize_filename(Path(file_path).stem, fallback="manual").lower()
    return ""


def legacy_deck_key_for(deck: dict | None, file_path: Path | None) -> str:
    """How a deck was keyed before it had an id: by name, else file stem, else record.

    Kept because it is the name of any repo written by an earlier build, and
    because a deck with no id yet still has to be asked about by *something*.
    """
    key = adoptable_legacy_key(deck, file_path)
    if key:
        return key
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


@dataclass(frozen=True)
class VersionPreview:
    """One version's decklist and its change against a chosen baseline."""

    sha: str
    text: str
    #: What ``diff`` is taken against -- the pinned baseline, else the parent.
    base_sha: str | None = None
    diff: DeckDiff | None = None


@dataclass(frozen=True)
class HistorySnapshot:
    """Everything the history view shows, read in one pass.

    The view needs the graph, the branch list, which branch ``HEAD`` is on, and
    the selected version's decklist and diff. Read separately those are four
    trips into the repo; gathered here they are one, which is what lets the
    whole read happen on a background thread and arrive as a single answer.
    """

    graph: tuple[GraphCommit, ...] = ()
    branches: tuple[str, ...] = ()
    current_branch: str | None = None
    preview: VersionPreview | None = None

    @property
    def selected_sha(self) -> str | None:
        return self.preview.sha if self.preview is not None else None


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

        # The tip is read once and reused: the unchanged check and the auto
        # summary both want it, and each read walked the whole history.
        with self.vcs_repo.read_session(deck_key):
            tip_text = self.current_version_text(deck_key)
            if tip_text is not None and normalize_decklist(tip_text) == normalize_decklist(
                deck_text
            ):
                logger.debug(f"Deck unchanged, no version recorded: {deck_key}")
                return None
            resolved = message or self._summarize(tip_text, deck_text)

        # Outside the session: a commit must not reuse a view of the object
        # store taken before it.
        return self.vcs_repo.commit_deck(deck_key, deck_text, resolved)

    def describe_change(self, deck_key: str, deck_text: str) -> str:
        """An auto-summary of ``deck_text`` against the current tip.

        This is what makes a graph readable without the user having typed a
        commit message for every save -- the node says "+2 Fable, -2 Consider"
        rather than "save 14".
        """
        with self.vcs_repo.read_session(deck_key):
            return self._summarize(self.current_version_text(deck_key), deck_text)

    @staticmethod
    def _summarize(tip_text: str | None, deck_text: str) -> str:
        """The auto summary, against a tip the caller has already read."""
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
        """The decklist at the current ``HEAD``, or ``None`` with no history.

        Reads the ref rather than walking the history for the commit that
        matches it: every save asks this, and the walk decodes every commit
        object the deck has.
        """
        sha = self.vcs_repo.head_sha(deck_key)
        if sha is None:
            return None
        return self.vcs_repo.read_commit_text(deck_key, sha)

    def version_text(self, deck_key: str, sha: str) -> str:
        """The decklist stored in one version. Never touches the user's file."""
        return self.vcs_repo.read_commit_text(deck_key, sha)

    def build_graph(self, deck_key: str) -> list[GraphCommit]:
        """Every version of the deck, newest first, with its change summary.

        The whole walk runs under one read session, which is what makes it
        affordable: it reads a blob per commit rather than re-opening the repo
        twice per commit and reading every blob twice.
        """
        graph: list[GraphCommit] = []
        with self.vcs_repo.read_session(deck_key):
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

    def read_history(
        self,
        deck_key: str,
        *,
        selected_sha: str | None = None,
        baseline_sha: str | None = None,
    ) -> HistorySnapshot:
        """The whole history view in one read, safe to call off the UI thread.

        ``selected_sha`` is the version to preview; it falls back to ``HEAD``
        when it is ``None`` or names a commit this deck's history does not have
        -- which is what happens when the loaded deck changes under a selection.
        A repo that cannot be read at all comes back empty rather than raising,
        because a broken history must not take the tab down with it.
        """
        try:
            with self.vcs_repo.read_session(deck_key):
                graph = self.build_graph(deck_key)
                branches = tuple(self.list_branches(deck_key))
                current = self.current_branch(deck_key)
                preview = self._read_preview(deck_key, graph, selected_sha, baseline_sha)
        except Exception as exc:  # noqa: BLE001 - a broken repo must not kill the tab
            logger.warning(f"Could not read deck history for {deck_key}: {exc}")
            return HistorySnapshot()
        return HistorySnapshot(
            graph=tuple(graph),
            branches=branches,
            current_branch=current,
            preview=preview,
        )

    def read_preview(
        self,
        deck_key: str,
        graph: Sequence[GraphCommit],
        sha: str | None,
        baseline_sha: str | None = None,
    ) -> VersionPreview | None:
        """One version's decklist and diff, against a graph already in hand."""
        try:
            with self.vcs_repo.read_session(deck_key):
                return self._read_preview(deck_key, graph, sha, baseline_sha)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"Could not read version {(sha or '?')[:7]}: {exc}")
            return None

    def _read_preview(
        self,
        deck_key: str,
        graph: Sequence[GraphCommit],
        sha: str | None,
        baseline_sha: str | None,
    ) -> VersionPreview | None:
        """Assumes a read session is already open."""
        if not graph:
            return None
        entry = next((g for g in graph if g.sha == sha), None)
        if entry is None:
            entry = next((g for g in graph if g.commit.is_head), graph[0])

        text = self.version_text(deck_key, entry.sha)
        base = baseline_sha or (entry.commit.parents[0] if entry.commit.parents else None)
        if base is None or base == entry.sha:
            return VersionPreview(sha=entry.sha, text=text)
        return VersionPreview(
            sha=entry.sha,
            text=text,
            base_sha=base,
            diff=self.diff(deck_key, base, entry.sha),
        )

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
        with self.vcs_repo.read_session(deck_key):
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
            head = self.vcs_repo.head_sha(deck_key)
            if head is not None:
                created = self.vcs_repo.create_branch(deck_key, as_branch, head)
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


#: Written out because three of these names are only here to be re-exported.
#: ``CardDelta``, ``DeckCommit`` and ``DeckDiff`` are the repository's own
#: dataclasses, and this module is where the rest of the app is meant to reach
#: them: a widget that has been handed a :class:`DeckDiff` by this service has
#: to be able to name its parts without importing a repository package, which
#: would put the widget layer one import away from git. Re-exporting them here
#: costs nothing -- the service already returns them -- and keeps the layering
#: readable from the import line alone.
__all__ = [
    "CardDelta",
    "DeckCommit",
    "DeckDiff",
    "DeckVcsService",
    "ExternalEdit",
    "ExternalEditStatus",
    "GraphCommit",
    "HistorySnapshot",
    "VersionPreview",
    "adoptable_legacy_key",
    "deck_key_for",
    "get_deck_vcs_service",
    "legacy_deck_key_for",
    "reset_deck_vcs_service",
]
