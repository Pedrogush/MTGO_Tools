"""Shared ``self`` contract that the :class:`DeckVcsRepository` mixins assume.

Each mixin in this package uses :class:`DeckVcsRepositoryProto` as a
``TYPE_CHECKING``-only base so type checkers can see the attributes that are
initialized on ``DeckVcsRepository`` itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, Protocol


class DeckVcsRepositoryProto(Protocol):
    """Cross-mixin ``self`` surface for ``DeckVcsRepository``."""

    _vcs_root: Path
    _legacy_root: Path

    # ``store`` contributes these; the other mixins all go through them.
    def repo_path(self, deck_key: str) -> Path: ...

    def has_repo(self, deck_key: str) -> bool: ...

    def adopt_legacy_repo(self, deck_key: str, legacy_key: str) -> bool: ...

    def _open(self, deck_key: str, *, create: bool = False) -> AbstractContextManager[Any]: ...

    def read_session(self, deck_key: str) -> AbstractContextManager[None]: ...

    def _session_blob(self, deck_key: str, sha: str) -> str | None: ...

    def _remember_blob(self, deck_key: str, sha: str, text: str) -> None: ...

    def _deck_file(self, deck_key: str) -> Path: ...

    # ``commits`` contributes these; ``branches`` and ``diffs`` read them.
    def read_commit_text(self, deck_key: str, sha: str) -> str: ...

    def iter_commits(self, deck_key: str) -> Iterator[Any]: ...

    def head_sha(self, deck_key: str) -> str | None: ...
