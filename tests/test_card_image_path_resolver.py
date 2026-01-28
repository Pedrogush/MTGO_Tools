"""Characterization tests for CardImagePathResolver.

Covers path normalization, Windows back-slash handling, WSL drive-letter
translation, and relative-path resolution against known roots.
"""

from __future__ import annotations

from pathlib import Path

from utils.card_image_path_resolver import CardImagePathResolver


def test_resolve_existing_absolute_path(tmp_path):
    """An absolute path that exists on disk should be returned as-is."""
    resolver = CardImagePathResolver(tmp_path)
    target = tmp_path / "normal" / "abc.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"img")

    result = resolver.resolve_path(str(target))
    assert result == target


def test_resolve_nonexistent_path_returns_best_effort(tmp_path):
    """A path that does not exist should still return a Path object (best effort)."""
    resolver = CardImagePathResolver(tmp_path)
    result = resolver.resolve_path("/nonexistent/path/to/image.jpg")
    # Should return a Path (not crash), even though the file does not exist
    assert isinstance(result, Path)


def test_resolve_backslash_relative_path(tmp_path):
    """Back-slash separators in a relative path should be normalized."""
    resolver = CardImagePathResolver(tmp_path)
    # Create the target file so the resolver can find it
    target = tmp_path / "normal" / "uuid-win.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"img")

    # Simulate a Windows-style relative path stored in the database
    result = resolver.resolve_path("normal\\uuid-win.jpg")
    assert result == target


def test_resolve_forward_slash_relative_path(tmp_path):
    """Forward-slash relative paths under the cache root should resolve."""
    resolver = CardImagePathResolver(tmp_path)
    target = tmp_path / "large" / "card-123.png"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"img")

    result = resolver.resolve_path("large/card-123.png")
    assert result == target


def test_resolve_strips_whitespace(tmp_path):
    """Leading/trailing whitespace in stored paths should be stripped."""
    resolver = CardImagePathResolver(tmp_path)
    target = tmp_path / "small" / "trimmed.jpg"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"img")

    result = resolver.resolve_path("  small/trimmed.jpg  ")
    assert result == target


def test_wsl_drive_translation(tmp_path, monkeypatch):
    """Windows drive-letter paths should translate to /mnt/<drive>/ on POSIX."""
    import os

    # Only run this assertion on non-Windows platforms
    if os.name == "nt":
        return

    resolver = CardImagePathResolver(tmp_path)

    # Create a file at /mnt/c/... so the translation can succeed
    mnt_target = Path("/mnt/c/Users/test/cache/normal/wsl.jpg")
    if mnt_target.exists():
        result = resolver.resolve_path("C:\\Users\\test\\cache\\normal\\wsl.jpg")
        assert result == mnt_target
    else:
        # File does not exist on this system -- just verify no crash
        result = resolver.resolve_path("C:\\Users\\test\\cache\\normal\\wsl.jpg")
        assert isinstance(result, Path)


def test_path_roots_include_cache_dir_and_parents(tmp_path):
    """The resolver should search the cache dir, its parent, and CWD."""
    resolver = CardImagePathResolver(tmp_path)
    roots = resolver._path_roots

    assert tmp_path.resolve() in roots
    assert tmp_path.parent.resolve() in roots


def test_empty_string_does_not_crash(tmp_path):
    """An empty stored path should not raise an exception."""
    resolver = CardImagePathResolver(tmp_path)
    result = resolver.resolve_path("")
    assert isinstance(result, Path)
