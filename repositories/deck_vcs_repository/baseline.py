"""Seeding a deck's history with an archetype baseline as its root commit.

Making the baseline the *root commit* rather than a pointer beside the history
is what collapses "diff vs. archetype baseline" into an ordinary ancestor diff.
There is then no second concept to keep in sync, and the baseline participates
in the graph like any other version because it *is* one.

Two properties are load-bearing, and both are enforced here rather than left to
callers:

**The root is deterministic.** A git commit's sha hashes its tree, parents,
author, committer, timestamps and message. Phase 1 gives every deck its own
repo, so a literally shared commit object is not available -- but fixing all of
those inputs gets the same thing for free: two decks built from the same
baseline land on the *same root sha* in their separate repos. That is the
"well-defined common ancestor across players" the design asked for, and it costs
one constant.

**The root is never rewritten.** A baseline drifts as the metagame moves, and
re-rooting a deck that already has commits would rewrite history underneath the
player's own versions -- the class of complexity the "no merging, ever" rule
exists to keep out. :meth:`seed_baseline_root` therefore refuses on any repo
that already holds a commit, rather than trusting callers to check first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from repositories.deck_vcs_repository.normalize import normalize_decklist
from repositories.deck_vcs_repository.store import DEFAULT_BRANCH
from utils.atomic_io import atomic_write_text

if TYPE_CHECKING:
    from repositories.deck_vcs_repository.protocol import DeckVcsRepositoryProto

    _Base = DeckVcsRepositoryProto
else:
    _Base = object

#: The identity every baseline root is authored by. Distinct from the app's own
#: committer so a glance at the graph says the root did not come from a save.
BASELINE_IDENTITY = b"MTGO Tools Baseline <baseline@localhost>"

#: A fixed point in time for every baseline root, 2020-01-01T00:00:00Z.
#:
#: The wall-clock moment a baseline happened to be computed is exactly the input
#: that would make two players' roots differ for no reason, so it is not used.
#: What remains in the sha is the decklist and the archetype -- which is the
#: identity the root should have.
BASELINE_EPOCH = 1577836800

#: Timezone offset, in seconds, pinned for the same reason as the epoch.
BASELINE_TIMEZONE = 0


class BaselineRootError(RuntimeError):
    """Raised when a baseline root cannot be created for a deck."""


def baseline_message(archetype: str, mtg_format: str) -> str:
    """The root commit's message.

    Kept to the archetype and format alone. Anything that varies between two
    computations of the same baseline -- pool size, the day it was run -- would
    enter the sha and split roots that ought to coincide, so those facts are
    reported next to the baseline instead of inside its commit.
    """
    return f"Archetype baseline: {archetype} ({mtg_format})"


class BaselineMixin(_Base):
    """Create a deck repo whose root commit is an archetype baseline."""

    def seed_baseline_root(
        self,
        deck_key: str,
        baseline_text: str,
        *,
        archetype: str,
        mtg_format: str,
    ) -> str:
        """Create ``deck_key``'s repo with the baseline as its only commit.

        Returns the root sha. Raises :class:`BaselineRootError` if the deck
        already has any history -- re-rooting is never allowed.
        """
        from dulwich import porcelain

        if not baseline_text.strip():
            raise BaselineRootError("Refusing to root a deck at an empty baseline")

        if self.has_commits(deck_key):
            raise BaselineRootError(
                f"{deck_key!r} already has version history; a baseline root cannot be "
                "added retroactively without rewriting the commits above it"
            )

        normalized = normalize_decklist(baseline_text)
        message = baseline_message(archetype, mtg_format)

        with self._open(deck_key, create=True) as repo:
            deck_file = self._deck_file(deck_key)
            atomic_write_text(deck_file, normalized)
            porcelain.add(repo.path, paths=[str(deck_file)])
            sha = porcelain.commit(
                repo.path,
                message=message.encode("utf-8"),
                committer=BASELINE_IDENTITY,
                author=BASELINE_IDENTITY,
                author_timestamp=BASELINE_EPOCH,
                author_timezone=BASELINE_TIMEZONE,
                commit_timestamp=BASELINE_EPOCH,
                commit_timezone=BASELINE_TIMEZONE,
            )

        resolved = sha.decode("ascii") if isinstance(sha, bytes) else str(sha)
        logger.info(
            f"Deck rooted at archetype baseline: {deck_key} {resolved[:7]} "
            f"({archetype}/{mtg_format})"
        )
        return resolved

    def root_commit_sha(self, deck_key: str) -> str | None:
        """The parentless commit at the bottom of ``deck_key``'s history.

        With no merging there is exactly one, so "the root" is well defined --
        this is what a caller pins to diff the working deck against its
        archetype baseline.
        """
        if not self.has_repo(deck_key):
            return None
        for commit in self.iter_commits(deck_key):
            if not commit.parents:
                return str(commit.sha)
        return None

    def is_baseline_root(self, deck_key: str, sha: str) -> bool:
        """True when ``sha`` is a commit this module authored."""
        if not self.has_repo(deck_key):
            return False
        with self._open(deck_key) as repo:
            try:
                commit = repo[sha.encode("ascii")]
            except KeyError:
                return False
            return bytes(commit.author) == BASELINE_IDENTITY


__all__ = [
    "BASELINE_EPOCH",
    "BASELINE_IDENTITY",
    "BASELINE_TIMEZONE",
    "BaselineMixin",
    "BaselineRootError",
    "DEFAULT_BRANCH",
    "baseline_message",
]
