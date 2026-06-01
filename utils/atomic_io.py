"""Atomic file writes with in-process locking."""

from __future__ import annotations

import os
import tempfile
import threading
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import msgspec.json

_lock_registry: dict[Path, threading.RLock] = {}
_lock_registry_lock = threading.Lock()

# Windows briefly holds a handle on the destination (antivirus, Search
# indexer, or a concurrent reader) which makes os.replace fail with
# PermissionError / WinError 5. The lock is transient, so retry with a
# short backoff before giving up.
_REPLACE_RETRIES = 5
_REPLACE_BACKOFF = 0.05


def _replace_with_retry(src: Path, dst: Path) -> None:
    for attempt in range(_REPLACE_RETRIES):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRIES - 1:
                raise
            time.sleep(_REPLACE_BACKOFF * (attempt + 1))


def _get_path_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _lock_registry_lock:
        lock = _lock_registry.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _lock_registry[resolved] = lock
        return lock


@contextmanager
def locked_path(path: Path) -> Iterator[None]:
    lock = _get_path_lock(path)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def _fsync_dir(directory: Path) -> None:
    try:
        fd = os.open(directory, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(path):
        fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp_file = Path(tmp_path)
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            _replace_with_retry(tmp_file, path)
            _fsync_dir(path.parent)
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass


def atomic_write_stream(path: Path, chunks: Iterable[bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(path):
        fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        tmp_file = Path(tmp_path)
        try:
            with os.fdopen(fd, "wb") as fh:
                for chunk in chunks:
                    fh.write(chunk)
                fh.flush()
                os.fsync(fh.fileno())
            _replace_with_retry(tmp_file, path)
            _fsync_dir(path.parent)
        finally:
            if tmp_file.exists():
                try:
                    tmp_file.unlink()
                except OSError:
                    pass


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    atomic_write_bytes(path, text.encode(encoding))


def atomic_write_json(
    path: Path,
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = False,
    separators: tuple[str, str] | None = None,
) -> None:
    # msgspec.json.encode always produces compact UTF-8 bytes (no ASCII escaping).
    # The ``ensure_ascii`` parameter is accepted for API compatibility but ignored
    # because msgspec always uses UTF-8 encoding (never escapes non-ASCII chars).
    raw: bytes = msgspec.json.encode(payload)
    if indent is not None:
        raw = msgspec.json.format(raw, indent=indent)
    # When callers explicitly request compact output via ``separators``,
    # ``indent`` is typically None so the branch above is skipped and we
    # already have compact bytes – nothing more to do.
    atomic_write_bytes(path, raw)
