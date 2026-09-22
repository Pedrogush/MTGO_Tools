"""Named pointers into a deck's history, and moving between them.

The doc this feature comes from calls detached ``HEAD`` "a real risk": a commit
made while ``HEAD`` points at a bare sha is reachable from no ref, and git will
eventually collect it -- a save the player made, silently gone.

This package closes that hole by never detaching at all. :meth:`BranchesMixin.checkout`
onto a commit that is not already a branch tip *creates a branch there first*
and switches to that, so ``HEAD`` is symbolic at every moment and every commit
is reachable from a ref the instant it exists. The doc's alternative -- detach
now, ask for a branch name at save time -- leaves a window where a crash, or a
save path that forgets to ask, loses work; this has no such window.

No merging exists here, by design. Branches that diverge stay diverged forever,
related only by shared ancestry.
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

_HEADS = b"refs/heads/"

# git refuses these outright (git-check-ref-format), so a deck or card name that
# wandered into a branch name is reduced rather than trusted -- an illegal ref
# name produces a repo that cannot be opened again.
_ILLEGAL_REF_CHARS = frozenset(chr(code) for code in range(0x21)) | frozenset(
    "~^:?*[]" + chr(0x5C) + chr(0x7F)
)

#: git reserves this for the reflog syntax (``main@{yesterday}``) and refuses any
#: ref name containing it, whatever the rest of the name looks like.
_REFLOG_MARKER = "@{"

#: git's own lock file for a ref is ``<ref>.lock``, so no path component of a ref
#: may end in it -- ``wip.lock`` is a legal filename and an illegal branch.
_LOCK_SUFFIX = ".lock"


def _collapse_slashes(name: str) -> str:
    while "//" in name:
        name = name.replace("//", "/")
    return name


def _without_lock_suffix(component: str) -> str:
    while component.endswith(_LOCK_SUFFIX):
        component = component[: -len(_LOCK_SUFFIX)]
    return component


def sanitize_branch_name(name: str, fallback: str = "branch") -> str:
    """``name`` reduced to something git will accept as a branch name.

    The character scan above is not the whole of ``git-check-ref-format``: two
    of its rules are about sequences rather than characters, and a name that
    breaks either one survives every substitution here and is only rejected when
    the ref is created, by which point the user has typed a name and lost it.
    """
    cleaned = "".join("-" if ch in _ILLEGAL_REF_CHARS else ch for ch in name.strip())
    cleaned = cleaned.replace(_REFLOG_MARKER, "-")
    while ".." in cleaned:
        cleaned = cleaned.replace("..", "-")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    cleaned = _collapse_slashes(cleaned).strip("/.-")
    # Last, so that a trailing dot stripped just above cannot expose a ".lock"
    # again -- and first-in-reverse, since dropping one can empty a component.
    cleaned = "/".join(_without_lock_suffix(part) for part in cleaned.split("/"))
    return _collapse_slashes(cleaned).strip("/.-") or fallback


class BranchesMixin(_Base):
    """List, create, and switch the branches of a deck's history."""

    def list_branches(self, deck_key: str) -> list[str]:
        if not self.has_repo(deck_key):
            return []
        with self._open(deck_key) as repo:
            return sorted(
                ref[len(_HEADS) :].decode("utf-8")
                for ref in repo.refs.as_dict()
                if ref.startswith(_HEADS)
            )

    def current_branch(self, deck_key: str) -> str | None:
        """The branch ``HEAD`` points at, or ``None`` when there is no history yet."""
        if not self.has_repo(deck_key):
            return None
        with self._open(deck_key) as repo:
            ref = repo.refs.follow(b"HEAD")[0]
            target = ref[1] if len(ref) > 1 else ref[0]
            if target and target.startswith(_HEADS):
                return str(target[len(_HEADS) :].decode("utf-8"))
        return None

    def branch_tips(self, deck_key: str) -> dict[str, str]:
        """Branch name -> the sha it points at."""
        if not self.has_repo(deck_key):
            return {}
        with self._open(deck_key) as repo:
            return {
                ref[len(_HEADS) :].decode("utf-8"): sha.decode("ascii")
                for ref, sha in repo.refs.as_dict().items()
                if ref.startswith(_HEADS)
            }

    def unique_branch_name(self, deck_key: str, desired: str) -> str:
        """``desired``, suffixed until it collides with no existing branch."""
        base = sanitize_branch_name(desired)
        existing = set(self.list_branches(deck_key))
        if base not in existing:
            return base
        index = 2
        while f"{base}-{index}" in existing:
            index += 1
        return f"{base}-{index}"

    def create_branch(self, deck_key: str, name: str, at_sha: str) -> str:
        """Create a branch called ``name`` pointing at ``at_sha``; return its name."""
        from dulwich import porcelain

        resolved = self.unique_branch_name(deck_key, name)
        with self._open(deck_key) as repo:
            porcelain.branch_create(repo.path, resolved, objectish=at_sha)
        logger.info(f"Deck branch created: {deck_key} {resolved} at {at_sha[:7]}")
        return resolved

    def checkout(self, deck_key: str, sha: str) -> tuple[str, str]:
        """Move ``HEAD`` onto ``sha``, branching first if it is not already a tip.

        Returns ``(branch_name, decklist_text)``. The caller is responsible for
        writing that text to the user's real ``.txt`` -- this only moves the
        mirror, because the mirror is the only thing this layer owns.
        """
        tips = self.branch_tips(deck_key)
        target = next((name for name, tip in sorted(tips.items()) if tip == sha), None)
        if target is None:
            # Not a tip: branching here is what keeps HEAD symbolic, so the next
            # save cannot land on an unreferenced commit.
            target = self.create_branch(deck_key, f"branch-from-{sha[:7]}", sha)
        return target, self.switch_branch(deck_key, target)

    def switch_branch(self, deck_key: str, name: str) -> str:
        """Point ``HEAD`` at branch ``name`` and sync the mirror's working file.

        Returns the branch's decklist text.
        """
        from dulwich import porcelain

        ref = _HEADS + name.encode("utf-8")
        with self._open(deck_key) as repo:
            if ref not in repo.refs.as_dict():
                raise KeyError(f"No such deck branch: {name}")
            sha = repo.refs[ref].decode("ascii")
            repo.refs.set_symbolic_ref(b"HEAD", ref)

        text = self.read_commit_text(deck_key, sha)
        # The mirror's working file and index have to match the new tip, or the
        # next commit would be built from the branch we just left.
        deck_file = self._deck_file(deck_key)
        atomic_write_text(deck_file, normalize_decklist(text))
        with self._open(deck_key) as repo:
            porcelain.add(repo.path, paths=[str(deck_file)])
        logger.info(f"Deck branch checked out: {deck_key} {name} ({sha[:7]})")
        return text

    def default_branch_name(self) -> str:
        return DEFAULT_BRANCH
