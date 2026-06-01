"""Tests for atomic file writes, including Windows transient-lock retries."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import utils.atomic_io as atomic_io
from utils.atomic_io import atomic_write_bytes, atomic_write_json, atomic_write_text


def test_atomic_write_bytes_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    atomic_write_bytes(target, b"hello")
    assert target.read_bytes() == b"hello"


def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    atomic_write_json(target, {"a": 1, "b": [1, 2, 3]})
    assert target.read_text(encoding="utf-8").strip().startswith("{")
    assert '"a"' in target.read_text(encoding="utf-8")


def test_atomic_write_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    atomic_write_text(target, "first")
    atomic_write_text(target, "second")
    assert target.read_text(encoding="utf-8") == "second"


def test_replace_retries_on_transient_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A transient PermissionError (Windows WinError 5) should be retried."""
    target = tmp_path / "data.txt"
    target.write_text("old", encoding="utf-8")

    real_replace = os.replace
    calls = {"n": 0}

    def flaky_replace(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] < 3:
            raise PermissionError(5, "Acesso negado")
        real_replace(src, dst)

    monkeypatch.setattr(atomic_io.os, "replace", flaky_replace)
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _seconds: None)

    atomic_write_text(target, "new")

    assert calls["n"] == 3
    assert target.read_text(encoding="utf-8") == "new"


def test_replace_reraises_after_exhausting_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A persistent PermissionError should surface after all retries."""
    target = tmp_path / "data.txt"

    def always_denied(src: object, dst: object) -> None:
        raise PermissionError(5, "Acesso negado")

    monkeypatch.setattr(atomic_io.os, "replace", always_denied)
    monkeypatch.setattr(atomic_io.time, "sleep", lambda _seconds: None)

    with pytest.raises(PermissionError):
        atomic_write_text(target, "new")
