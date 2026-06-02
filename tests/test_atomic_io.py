"""Tests for atomic file writes, including Windows transient-lock retries."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

import utils.atomic_io as atomic_io
from utils.atomic_io import (
    atomic_write_bytes,
    atomic_write_json,
    atomic_write_stream,
    atomic_write_text,
)


def test_atomic_write_bytes_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.bin"
    atomic_write_bytes(target, b"hello")
    assert target.read_bytes() == b"hello"


def test_atomic_write_json_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    payload = {"a": 1, "b": [1, 2, 3]}
    atomic_write_json(target, payload)
    contents = target.read_text(encoding="utf-8")
    # Full roundtrip: every key/value (incl. the nested list) must survive.
    assert json.loads(contents) == payload
    # The default indent=2 branch must produce pretty-printed, indented output.
    assert "\n" in contents
    assert "\n  " in contents


def test_atomic_write_json_compact(tmp_path: Path) -> None:
    """indent=None must skip the format() branch and emit compact bytes."""
    target = tmp_path / "data.json"
    payload = {"a": 1, "b": [1, 2, 3]}
    atomic_write_json(target, payload, indent=None)
    contents = target.read_text(encoding="utf-8")
    assert json.loads(contents) == payload
    assert "\n" not in contents


def test_atomic_write_stream_roundtrip(tmp_path: Path) -> None:
    target = tmp_path / "stream.bin"
    atomic_write_stream(target, [b"foo", b"bar", b"baz"])
    assert target.read_bytes() == b"foobarbaz"


def test_atomic_write_stream_overwrites_existing(tmp_path: Path) -> None:
    target = tmp_path / "stream.bin"
    target.write_bytes(b"old contents")
    atomic_write_stream(target, [b"new", b"-", b"data"])
    assert target.read_bytes() == b"new-data"


def test_atomic_write_creates_parent_directories(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "deeper" / "data.txt"
    atomic_write_text(target, "payload")
    assert target.read_text(encoding="utf-8") == "payload"


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


def test_get_path_lock_is_stable_across_spellings(tmp_path: Path) -> None:
    """Different Path spellings of one file must share a single lock."""
    target = tmp_path / "data.txt"
    target.write_text("x", encoding="utf-8")

    lock_a = atomic_io._get_path_lock(target)
    lock_b = atomic_io._get_path_lock(tmp_path / "." / "data.txt")
    assert lock_a is lock_b


def test_locked_path_acquires_and_releases(tmp_path: Path) -> None:
    target = tmp_path / "data.txt"
    target.write_text("x", encoding="utf-8")
    lock = atomic_io._get_path_lock(target)

    with atomic_io.locked_path(target):
        # An RLock is reentrant, so a non-blocking acquire from the same
        # thread succeeds while held; balance it with a release.
        assert lock.acquire(blocking=False)
        lock.release()

    # After the context manager exits the lock must be fully released.
    assert lock.acquire(blocking=False)
    lock.release()


def test_concurrent_writes_to_same_path_are_not_interleaved(tmp_path: Path) -> None:
    """Concurrent writers to one path serialize and never produce a torn file."""
    target = tmp_path / "data.txt"
    payloads = [str(i) * 2000 for i in range(20)]
    barrier = threading.Barrier(len(payloads))

    def writer(text: str) -> None:
        barrier.wait()
        atomic_write_text(target, text)

    threads = [threading.Thread(target=writer, args=(p,)) for p in payloads]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # The surviving file must be exactly one of the writers' payloads,
    # never a mix of two (which would indicate a non-atomic / unlocked write).
    assert target.read_text(encoding="utf-8") in payloads
