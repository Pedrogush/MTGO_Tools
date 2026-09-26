"""What changed between two versions of a deck.

Two shapes, because two things ask. The graph and the diff view want *cards* --
"+2 Fable of the Mirror-Breaker, -2 Consider" -- which is a comparison of count
per card name, not of lines. :func:`unified_lines` keeps the familiar text form
for the side-by-side view. Both read from the same normalized blobs, so neither
can report a change that is only a reordering.
"""

from __future__ import annotations

import difflib
from typing import TYPE_CHECKING

from repositories.deck_vcs_repository.models import CardDelta, DeckDiff
from repositories.deck_vcs_repository.normalize import normalize_decklist, parse_entries

if TYPE_CHECKING:
    from repositories.deck_vcs_repository.protocol import DeckVcsRepositoryProto

    _Base = DeckVcsRepositoryProto
else:
    _Base = object


def _counts(deck_text: str) -> dict[tuple[str, bool], float]:
    return {(entry.name, entry.is_sideboard): entry.count for entry in parse_entries(deck_text)}


def diff_decklists(before_text: str, after_text: str) -> DeckDiff:
    """The card-level difference between two decklists."""
    before = _counts(before_text)
    after = _counts(after_text)

    added: list[CardDelta] = []
    removed: list[CardDelta] = []
    changed: list[CardDelta] = []

    for key in sorted(set(before) | set(after), key=lambda k: (k[1], k[0].casefold())):
        name, is_sideboard = key
        old = before.get(key, 0.0)
        new = after.get(key, 0.0)
        if old == new:
            continue
        delta = CardDelta(name=name, before=old, after=new, is_sideboard=is_sideboard)
        if old == 0:
            added.append(delta)
        elif new == 0:
            removed.append(delta)
        else:
            changed.append(delta)

    return DeckDiff(added=tuple(added), removed=tuple(removed), changed=tuple(changed))


def unified_lines(
    before_text: str, after_text: str, *, before_label: str, after_label: str
) -> list[str]:
    """A unified text diff of the two decklists' canonical forms."""
    return list(
        difflib.unified_diff(
            normalize_decklist(before_text).splitlines(),
            normalize_decklist(after_text).splitlines(),
            fromfile=before_label,
            tofile=after_label,
            lineterm="",
        )
    )


class DiffsMixin(_Base):
    """Compare two commits, or a commit against text in hand."""

    def diff_commits(self, deck_key: str, base_sha: str, target_sha: str) -> DeckDiff:
        return diff_decklists(
            self.read_commit_text(deck_key, base_sha),
            self.read_commit_text(deck_key, target_sha),
        )

    def diff_against_text(self, deck_key: str, base_sha: str, deck_text: str) -> DeckDiff:
        return diff_decklists(self.read_commit_text(deck_key, base_sha), deck_text)

    def diff_from_parent(self, deck_key: str, sha: str, parent_sha: str | None) -> DeckDiff:
        """A commit's change against its parent; a root commit diffs against nothing."""
        after = self.read_commit_text(deck_key, sha)
        before = self.read_commit_text(deck_key, parent_sha) if parent_sha else ""
        return diff_decklists(before, after)

    def unified_diff(self, deck_key: str, base_sha: str, target_sha: str) -> list[str]:
        return unified_lines(
            self.read_commit_text(deck_key, base_sha),
            self.read_commit_text(deck_key, target_sha),
            before_label=base_sha[:7],
            after_label=target_sha[:7],
        )
