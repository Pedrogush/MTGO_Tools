"""Tests for filesystem base-data path resolution."""

from __future__ import annotations

import utils.constants.paths as paths


def test_default_base_dir_honors_env_override(tmp_path, monkeypatch):
    base_dir = tmp_path / "shared-data"

    monkeypatch.setenv(paths.BASE_DATA_DIR_ENV_VAR, str(base_dir))

    assert paths._default_base_dir() == base_dir.resolve()


def test_default_base_dir_uses_repo_root_for_regular_checkout(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    subdir = repo_root / "scripts"
    (repo_root / ".git").mkdir(parents=True)
    subdir.mkdir()

    monkeypatch.delenv(paths.BASE_DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(subdir)

    assert paths._default_base_dir() == repo_root.resolve()


def test_default_base_dir_uses_primary_repo_root_for_sibling_worktree(tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    worktree_root = tmp_path / "repo-issue-123"
    worktree_subdir = worktree_root / "scripts"
    gitdir = repo_root / ".git" / "worktrees" / "repo-issue-123"
    gitdir.mkdir(parents=True)
    worktree_subdir.mkdir(parents=True)
    (worktree_root / ".git").write_text(f"gitdir: {gitdir}\n", encoding="utf-8")

    monkeypatch.delenv(paths.BASE_DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(worktree_subdir)

    assert paths._default_base_dir() == repo_root.resolve()


def test_default_base_dir_uses_primary_repo_root_for_relative_worktree_gitdir(
    tmp_path, monkeypatch
):
    repo_root = tmp_path / "repo"
    worktree_root = repo_root / ".worktrees" / "issue-123"
    gitdir = repo_root / ".git" / "worktrees" / "issue-123"
    gitdir.mkdir(parents=True)
    worktree_root.mkdir(parents=True)
    (worktree_root / ".git").write_text(
        "gitdir: ../../.git/worktrees/issue-123\n", encoding="utf-8"
    )

    monkeypatch.delenv(paths.BASE_DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(worktree_root)

    assert paths._default_base_dir() == repo_root.resolve()
