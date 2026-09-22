"""Keep the test suite away from the user's real config/, cache/ and deck folder.

The app resolves its data dirs to the main checkout (see ``utils/constants/paths``),
so a test that reaches a real path writes to the developer's own settings and
caches. Patching the constants on ``utils.constants`` alone does not stop that,
because three kinds of reference keep the real path:

- a name imported at module load: ``from utils.constants import NOTES_STORE``,
  or an alias such as ``DECK_CACHE_DB = DECK_CACHE_DB_FILE``;
- a default argument, which Python evaluates once, when the function is defined:
  ``def __init__(self, db_path: Path = RADAR_CACHE_DB_FILE)``;
- work a test left running on a thread, which runs after the test's patches are
  undone.

:func:`redirect_bound_paths` rewrites the first two in every loaded project module.
The root conftest applies it once for the whole run (so late threads land in a
session tmp dir), and ``tests/ui/conftest.py`` layers a per-test redirect on top.
:func:`snapshot_real_data` backs the guard that fails the run if anything still
gets through, and :func:`real_paths_written_here` tells that guard which of the
changed files this process actually wrote -- the app resolves its data dirs to
the same checkout, so a developer running it alongside the suite otherwise fails
the run with a write no test made.

Import it as ``data_isolation`` (like ``test_helpers``), never ``tests.data_isolation``:
a second copy would record the already-patched paths as the "real" ones.
"""

from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path
from typing import Any

import pytest

# The root conftest imports this module before test_helpers, which is what used
# to put the repo root on sys.path. Plain ``pytest`` (as CI runs it) does not add
# the working directory the way ``python -m pytest`` does, so do it here too.
_repo_root_dir = str(Path(__file__).resolve().parent.parent)
if _repo_root_dir not in sys.path:
    sys.path.insert(0, _repo_root_dir)

import utils.constants as constants  # noqa: E402

# Recorded when the root conftest imports this module, before any fixture patches
# them: the user's real data dirs, and every path constant that points into them.
#: ``logs`` and ``data`` are here because ``ensure_base_dirs()`` -- which every
#: ``AppController`` runs -- creates them next to config/ and cache/. In a real
#: checkout they already exist, so nothing noticed; under a fresh
#: ``MTGO_TOOLS_BASE_DATA_DIR`` (what CI sees) the suite created both.
REAL_DATA_DIRS: dict[str, Path] = {
    "config": Path(constants.CONFIG_DIR),
    "cache": Path(constants.CACHE_DIR),
    "decks": Path(constants.DECKS_DIR),
    "logs": Path(constants.LOGS_DIR),
    "data": Path(constants.CARD_DATA_DIR),
}
_REAL_PATH_CONSTANTS = {
    name: value for name in dir(constants) if isinstance(value := getattr(constants, name), Path)
}
_TESTS_DIR = str(Path(__file__).resolve().parent)
_REPO_ROOT = str(Path(__file__).resolve().parent.parent)

# The session-wide tmp data dirs, once the root conftest has made them.
session_data_dirs: dict[str, Path] = {}

# Module name -> where it holds a real data path, found the first time it is seen.
_real_path_sites: dict[str, list[tuple[Any, str]]] = {}


def _path_key(path: Path) -> str:
    """How ``Path`` equality sees *path*: its string, case-folded where the OS folds case."""
    return os.path.normcase(os.fspath(path))


def _is_at_or_under(value: Path, directory: Path) -> bool:
    """``value == directory or directory in value.parents``, without building the parents.

    It runs for every path site on every UI test, and ``Path.parents`` builds a
    new ``Path`` per level each time. Comparing normalised strings answers the
    same question for a fraction of the cost.
    """
    value_key = _path_key(value)
    directory_key = _path_key(directory)
    return value_key == directory_key or value_key.startswith(directory_key.rstrip(os.sep) + os.sep)


def _under_real_data(value: object) -> bool:
    return isinstance(value, Path) and any(
        _is_at_or_under(value, real_dir) for real_dir in REAL_DATA_DIRS.values()
    )


def rebase(value: object, roots: dict[str, Path]) -> object:
    """*value* moved from the real (or session) data dir it sits under into *roots*."""
    if not isinstance(value, Path):
        return value
    for source_dirs in (REAL_DATA_DIRS, session_data_dirs):
        for key, source_dir in source_dirs.items():
            if _is_at_or_under(value, source_dir):
                return roots[key] / value.relative_to(source_dir)
    return value


def redirected_constants(roots: dict[str, Path]) -> dict[str, Path]:
    """Every ``utils.constants`` path under a real data dir, moved into *roots*."""
    return {
        name: rebase(value, roots)
        for name, value in _REAL_PATH_CONSTANTS.items()
        if _under_real_data(value)
    }


def _default_sites(func: Any) -> list[tuple[Any, str]]:
    sites = []
    if func.__defaults__ and any(_under_real_data(value) for value in func.__defaults__):
        sites.append((func, "__defaults__"))
    if func.__kwdefaults__ and any(
        _under_real_data(value) for value in func.__kwdefaults__.values()
    ):
        sites.append((func, "__kwdefaults__"))
    return sites


def _find_real_path_sites(module: Any) -> list[tuple[Any, str]]:
    """Module attributes and function/method defaults in *module* holding a real path."""
    sites: list[tuple[Any, str]] = []
    for name, value in list(vars(module).items()):
        if _under_real_data(value):
            sites.append((module, name))
        elif getattr(value, "__module__", None) != module.__name__:
            continue
        elif inspect.isfunction(value):
            sites += _default_sites(value)
        elif inspect.isclass(value):
            for member in list(vars(value).values()):
                func = getattr(member, "__func__", member)
                if inspect.isfunction(func):
                    sites += _default_sites(func)
    return sites


def redirect_bound_paths(monkeypatch: pytest.MonkeyPatch, roots: dict[str, Path]) -> None:
    """Point ``utils.constants`` and every real path bound in a project module at *roots*.

    Test modules are swept too (a test that imported a path constant by name
    should see the same path the code under test uses), but not the conftests or
    this module, which hold the real paths on purpose.
    """
    for name, value in redirected_constants(roots).items():
        monkeypatch.setattr(constants, name, value)
    for module in list(sys.modules.values()):
        module_file = getattr(module, "__file__", None) or ""
        if (
            module is constants
            or not module_file.startswith(_REPO_ROOT)
            or "site-packages" in module_file
            or (
                module_file.startswith(_TESTS_DIR)
                and os.path.basename(module_file) in ("conftest.py", "data_isolation.py")
            )
        ):
            continue
        sites = _real_path_sites.get(module.__name__)
        if sites is None:
            sites = _real_path_sites[module.__name__] = _find_real_path_sites(module)
        for owner, attr in sites:
            current = getattr(owner, attr)
            if attr == "__defaults__":
                patched: object = tuple(rebase(value, roots) for value in current)
            elif attr == "__kwdefaults__":
                patched = {key: rebase(value, roots) for key, value in current.items()}
            else:
                patched = rebase(current, roots)
            if patched != current:
                monkeypatch.setattr(owner, attr, patched)


# Real data paths *this* process opened for writing, recorded by the audit hook
# below. The guard compares them against the paths that changed during the run,
# because the run is not the only thing on the machine allowed to touch them:
# the app itself resolves its data dirs to the primary worktree (see
# ``utils/constants/paths``), so a developer running ``main.py --automation``
# while the suite runs has a deck/card cache writing underneath it. Without
# attribution the guard blames whichever test happened to be last.
_own_real_writes: set[str] = set()

# The audited events that can change a file. ``open`` covers ``builtins.open``,
# ``io.open`` (so ``Path.write_text`` too) and ``os.open``; ``sqlite3.connect``
# is separate because SQLite opens the database file in C, and it counts as a
# write even for a read-only query (closing a WAL database checkpoints it).
_WRITE_EVENTS = frozenset(
    {
        "open",
        "sqlite3.connect",
        "os.remove",
        "os.rename",
        "os.mkdir",
        "os.rmdir",
        "os.truncate",
        "shutil.copyfile",
        "shutil.move",
    }
)
_TWO_PATH_EVENTS = frozenset({"os.rename", "shutil.copyfile", "shutil.move"})
_WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
# Trailing separator so ``cache/`` does not also claim a sibling ``cache_old/``.
_REAL_DIR_PREFIXES = tuple(
    os.path.join(os.path.normcase(os.path.abspath(directory)), "")
    for directory in REAL_DATA_DIRS.values()
)


def normalized(path: object) -> str:
    """*path* as the absolute, case-folded string both sides of the guard compare."""
    return os.path.normcase(os.path.abspath(os.fspath(path)))  # type: ignore[arg-type]


def _note_write(path: object) -> None:
    try:
        target = normalized(path)
    except (TypeError, ValueError):
        return
    if target.startswith(_REAL_DIR_PREFIXES):
        _own_real_writes.add(target)


def _audit_real_writes(event: str, args: tuple) -> None:
    """Record real-data paths this process writes. Installed process-wide, once.

    Runs for every audited event, so it does the cheapest possible check first
    and never raises: an exception here would propagate into whatever the
    interpreter was auditing.
    """
    if event not in _WRITE_EVENTS:
        return
    try:
        if event == "open":
            path, mode, flags = args
            if isinstance(mode, str):
                if not any(char in mode for char in "wxa+"):
                    return
            elif isinstance(flags, int) and not flags & _WRITE_FLAGS:
                return
            _note_write(path)
        elif event in _TWO_PATH_EVENTS:
            _note_write(args[0])
            _note_write(args[1])
        else:
            _note_write(args[0])
    except Exception:
        # An audit hook must never raise: the exception would surface from the
        # unrelated call the interpreter was auditing.
        pass


sys.addaudithook(_audit_real_writes)


def real_paths_written_here() -> set[str]:
    """The real data paths this process has opened for writing so far."""
    return set(_own_real_writes)


def snapshot_real_data() -> dict[str, tuple[int, int]]:
    """``{path: (size, mtime_ns)}`` for every file under the real data dirs.

    Recursive, so card_images/ is covered (~7k files stat in well under 0.1 s).
    Size and mtime rather than bytes: cache/ holds multi-megabyte databases.
    """
    stats: dict[str, tuple[int, int]] = {}
    pending = [str(directory) for directory in REAL_DATA_DIRS.values()]
    while pending:
        try:
            entries = list(os.scandir(pending.pop()))
        except OSError:
            continue
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    pending.append(entry.path)
                else:
                    info = entry.stat(follow_symlinks=False)
                    stats[entry.path] = (info.st_size, info.st_mtime_ns)
            except OSError:
                continue
    return stats
