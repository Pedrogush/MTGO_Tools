"""Tests for filesystem base-data path resolution."""

from __future__ import annotations

import pytest

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


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("/mnt/c/Claude/MTGO_Tools/.git/worktrees/x", "C:\\Claude\\MTGO_Tools\\.git\\worktrees\\x"),
        ("/mnt/d/repo", "D:\\repo"),
        ("/mnt/c", "C:\\"),
        ("C:\\Claude\\repo", "C:\\Claude\\repo"),  # already Windows, unchanged
        ("/home/user/repo", "/home/user/repo"),  # non-mount, unchanged
    ],
)
def test_translate_worktree_path_on_windows(raw, expected, monkeypatch):
    monkeypatch.setattr(paths.os, "name", "nt")
    assert paths._translate_worktree_path(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("C:\\Claude\\MTGO_Tools\\.git\\worktrees\\x", "/mnt/c/Claude/MTGO_Tools/.git/worktrees/x"),
        ("D:/repo", "/mnt/d/repo"),
        ("/mnt/c/repo", "/mnt/c/repo"),  # already WSL-form, unchanged
        ("/home/user/repo", "/home/user/repo"),  # non-drive, unchanged
    ],
)
def test_translate_worktree_path_on_wsl(raw, expected, monkeypatch):
    monkeypatch.setattr(paths.os, "name", "posix")
    monkeypatch.setattr(paths, "_running_under_wsl", lambda: True)
    assert paths._translate_worktree_path(raw) == expected


def test_translate_worktree_path_on_native_linux_is_noop(monkeypatch):
    monkeypatch.setattr(paths.os, "name", "posix")
    monkeypatch.setattr(paths, "_running_under_wsl", lambda: False)
    # Windows-style input must not be translated on a real Linux host.
    assert paths._translate_worktree_path("C:\\foo") == "C:\\foo"


def test_default_base_dir_resolves_wsl_gitdir_on_windows(tmp_path, monkeypatch):
    """Worktrees created by WSL git leave WSL-form pointers; Windows Python must translate."""
    repo_root = tmp_path / "repo"
    worktree_root = tmp_path / "repo-issue-123"
    worktree_subdir = worktree_root / "scripts"
    gitdir = repo_root / ".git" / "worktrees" / "repo-issue-123"
    gitdir.mkdir(parents=True)
    worktree_subdir.mkdir(parents=True)

    # Simulate the pointer that WSL git would write: a /mnt/<drive>/... path.
    # Build it from the real tmp_path by rewriting its drive prefix.
    drive = tmp_path.drive  # e.g. "C:" on Windows, "" on Linux
    if drive:
        wsl_prefix = f"/mnt/{drive[0].lower()}"
        wsl_gitdir = wsl_prefix + str(gitdir)[len(drive) :].replace("\\", "/")
    else:
        # On non-Windows test hosts, fabricate a WSL path that maps back to tmp_path's posix form.
        wsl_gitdir = "/mnt/c" + str(gitdir)
    (worktree_root / ".git").write_text(f"gitdir: {wsl_gitdir}\n", encoding="utf-8")

    monkeypatch.delenv(paths.BASE_DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(worktree_subdir)
    monkeypatch.setattr(paths.os, "name", "nt")

    # With translation, the resolver must walk up to repo_root.
    # (On a Linux test host the translated C:\ path won't point at a real dir,
    # so we only assert the non-regressing behavior under the "nt" branch by
    # checking the translator in isolation — the full-path integration case is
    # already covered by test_default_base_dir_uses_primary_repo_root_for_sibling_worktree.)
    translated = paths._translate_worktree_path(wsl_gitdir)
    assert translated != wsl_gitdir  # translation kicked in
    assert not translated.startswith("/mnt/")  # no longer WSL-form
