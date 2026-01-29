"""Atomic file writes with in-process locking."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


_lock_registry: dict[Path, threading.RLock] = {}
_lock_registry_lock = threading.Lock()


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
            os.replace(tmp_file, path)
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
    data = json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, separators=separators)
    atomic_write_text(path, data)
