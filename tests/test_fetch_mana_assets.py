"""Tests for mana asset detection and the self-healing fetch helper."""

from __future__ import annotations

from pathlib import Path

import scripts.fetch_mana_assets as fetch


def _write_required_assets(target: Path) -> None:
    """Create the minimal file tree that counts as present mana assets."""
    (target / "fonts").mkdir(parents=True)
    (target / "fonts" / "mana.ttf").write_bytes(b"ttf")
    (target / "css").mkdir(parents=True)
    (target / "css" / "mana.min.css").write_text("/* css */", encoding="utf-8")
    (target / "svg").mkdir(parents=True)


def test_mana_assets_present_true_when_required_files_exist(tmp_path):
    _write_required_assets(tmp_path)
    assert fetch.mana_assets_present(tmp_path) is True


def test_mana_assets_present_false_when_missing(tmp_path):
    assert fetch.mana_assets_present(tmp_path / "nope") is False


def test_mana_assets_present_false_for_partial_dir(tmp_path):
    # A bare/half-cloned directory must not count as usable assets.
    (tmp_path / "fonts").mkdir()
    assert fetch.mana_assets_present(tmp_path) is False


def test_ensure_skips_clone_when_present(tmp_path, monkeypatch):
    target = tmp_path / "assets" / "mana"
    target.mkdir(parents=True)
    _write_required_assets(target)
    monkeypatch.setattr(fetch, "mana_assets_dir", lambda: target)

    def _fail_clone(*_args, **_kwargs):
        raise AssertionError("clone must not run when assets are present")

    monkeypatch.setattr(fetch, "_run_git_clone", _fail_clone)

    assert fetch.ensure_mana_assets(quiet=True) is True


def test_ensure_clones_when_missing(tmp_path, monkeypatch):
    target = tmp_path / "assets" / "mana"
    monkeypatch.setattr(fetch, "mana_assets_dir", lambda: target)

    calls: list[tuple[str, Path]] = []

    def _fake_clone(url, dest, depth=1):
        calls.append((url, dest))
        _write_required_assets(dest)

    monkeypatch.setattr(fetch, "_run_git_clone", _fake_clone)

    assert fetch.ensure_mana_assets(quiet=True) is True
    assert calls == [(fetch.DEFAULT_MANA_REPO, target)]
    assert fetch.mana_assets_present(target) is True


def test_ensure_replaces_partial_dir_before_clone(tmp_path, monkeypatch):
    target = tmp_path / "assets" / "mana"
    target.mkdir(parents=True)
    (target / "stale.txt").write_text("leftover", encoding="utf-8")
    monkeypatch.setattr(fetch, "mana_assets_dir", lambda: target)

    def _fake_clone(url, dest, depth=1):
        # git clone requires a clean target; the stale file must be gone.
        assert not (dest / "stale.txt").exists()
        _write_required_assets(dest)

    monkeypatch.setattr(fetch, "_run_git_clone", _fake_clone)

    assert fetch.ensure_mana_assets(quiet=True) is True


def test_ensure_returns_false_and_cleans_up_on_clone_failure(tmp_path, monkeypatch):
    import subprocess

    target = tmp_path / "assets" / "mana"
    monkeypatch.setattr(fetch, "mana_assets_dir", lambda: target)

    def _boom(url, dest, depth=1):
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "partial").write_text("x", encoding="utf-8")
        raise subprocess.CalledProcessError(1, ["git", "clone"])

    monkeypatch.setattr(fetch, "_run_git_clone", _boom)

    assert fetch.ensure_mana_assets(quiet=True) is False
    assert not target.exists()


def test_ensure_returns_false_when_clone_incomplete(tmp_path, monkeypatch):
    target = tmp_path / "assets" / "mana"
    monkeypatch.setattr(fetch, "mana_assets_dir", lambda: target)

    def _incomplete_clone(url, dest, depth=1):
        dest.mkdir(parents=True, exist_ok=True)  # clones nothing useful

    monkeypatch.setattr(fetch, "_run_git_clone", _incomplete_clone)

    assert fetch.ensure_mana_assets(quiet=True) is False
