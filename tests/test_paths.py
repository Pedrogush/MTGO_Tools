"""Tests for filesystem base-data path resolution."""

from __future__ import annotations

import os

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


@pytest.mark.skipif(
    os.name != "nt",
    reason="Full WSL-gitdir resolution needs a real Windows host where C:\\ paths exist on disk.",
)
def test_default_base_dir_resolves_wsl_gitdir_on_windows(tmp_path, monkeypatch):
    """Worktrees created by WSL git leave WSL-form pointers; Windows Python must translate.

    This is the real integration case: a ``/mnt/<drive>/...`` pointer must be
    translated back to a ``<drive>:\\...`` path that points at the on-disk
    primary repo, so ``_default_base_dir`` walks all the way up to ``repo_root``.
    It can only run on Windows, where the translated drive path resolves to a
    real directory; on POSIX hosts the translator itself is covered by
    ``test_translate_worktree_path_on_windows``.
    """
    repo_root = tmp_path / "repo"
    worktree_root = tmp_path / "repo-issue-123"
    worktree_subdir = worktree_root / "scripts"
    gitdir = repo_root / ".git" / "worktrees" / "repo-issue-123"
    gitdir.mkdir(parents=True)
    worktree_subdir.mkdir(parents=True)

    # Simulate the pointer that WSL git would write: a /mnt/<drive>/... path,
    # built from the real tmp_path by rewriting its drive prefix.
    drive = tmp_path.drive  # e.g. "C:" on Windows
    wsl_prefix = f"/mnt/{drive[0].lower()}"
    wsl_gitdir = wsl_prefix + str(gitdir)[len(drive) :].replace("\\", "/")
    (worktree_root / ".git").write_text(f"gitdir: {wsl_gitdir}\n", encoding="utf-8")

    monkeypatch.delenv(paths.BASE_DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.chdir(worktree_subdir)

    # With translation, the resolver must walk up to the primary repo root.
    assert paths._default_base_dir() == repo_root.resolve()


def test_default_base_dir_falls_back_to_repo_root_without_git_marker(tmp_path, monkeypatch):
    """An installed/copied checkout has no .git; the resolver falls back to the bundled root."""
    no_git_dir = tmp_path / "no-git" / "nested"
    no_git_dir.mkdir(parents=True)

    monkeypatch.delenv(paths.BASE_DATA_DIR_ENV_VAR, raising=False)
    monkeypatch.setattr(paths.sys, "frozen", False, raising=False)
    monkeypatch.chdir(no_git_dir)

    # cwd has no .git anywhere in its parents, so _base_dir_from_cwd() returns
    # None and _default_base_dir falls back to three levels up from paths.py.
    expected = paths.Path(paths.__file__).resolve().parent.parent.parent
    assert paths._base_dir_from_cwd() is None
    assert paths._default_base_dir() == expected


def test_resolve_gitdir_returns_none_for_non_gitdir_content(tmp_path):
    """A .git file whose content is not a 'gitdir:' pointer yields None (no crash)."""
    marker = tmp_path / ".git"
    marker.write_text("garbage\n", encoding="utf-8")

    assert paths._resolve_gitdir(marker) is None


def test_resolve_gitdir_returns_none_for_unreadable_marker(tmp_path, monkeypatch):
    """An unreadable .git marker is swallowed and reported as None."""
    marker = tmp_path / ".git"
    marker.write_text("gitdir: /somewhere\n", encoding="utf-8")

    def _raise_oserror(*args, **kwargs):
        raise OSError("unreadable")

    monkeypatch.setattr(paths.Path, "read_text", _raise_oserror)

    assert paths._resolve_gitdir(marker) is None


def test_primary_worktree_root_falls_back_on_malformed_marker(tmp_path):
    """A malformed .git pointer falls back to the worktree marker's own parent."""
    worktree_root = tmp_path / "worktree"
    worktree_root.mkdir()
    marker = worktree_root / ".git"
    marker.write_text("not-a-gitdir-pointer\n", encoding="utf-8")

    assert paths._primary_worktree_root_from_marker(marker) == worktree_root.resolve()


def test_running_under_wsl_false_on_non_linux(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "win32")
    assert paths._running_under_wsl() is False


def test_running_under_wsl_true_when_interop_env_set(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.setenv("WSL_INTEROP", "/run/WSL/123_interop")
    assert paths._running_under_wsl() is True


def test_running_under_wsl_true_when_proc_version_mentions_microsoft(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.delenv("WSL_INTEROP", raising=False)

    import io

    def _fake_open(*args, **kwargs):
        return io.StringIO("Linux version 5.15.0-microsoft-standard-WSL2")

    monkeypatch.setattr("builtins.open", _fake_open)
    assert paths._running_under_wsl() is True


def test_running_under_wsl_false_on_native_linux(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.delenv("WSL_INTEROP", raising=False)

    import io

    def _fake_open(*args, **kwargs):
        return io.StringIO("Linux version 6.6.0-generic")

    monkeypatch.setattr("builtins.open", _fake_open)
    assert paths._running_under_wsl() is False


def test_running_under_wsl_false_when_proc_version_unreadable(monkeypatch):
    monkeypatch.setattr(paths.sys, "platform", "linux")
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    monkeypatch.delenv("WSL_INTEROP", raising=False)

    def _raise_oserror(*args, **kwargs):
        raise OSError("no /proc/version")

    monkeypatch.setattr("builtins.open", _raise_oserror)
    assert paths._running_under_wsl() is False
