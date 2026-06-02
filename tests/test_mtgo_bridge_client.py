import multiprocessing as mp
import os
import queue as queue_mod
import stat
import sys
import textwrap
from pathlib import Path

import pytest

from services.mtgo_bridge_service import client as mtgo_bridge_client
from services.mtgo_bridge_service import commands as bridge_commands
from services.mtgo_bridge_service import watch as bridge_watch


def test_missing_bridge_path_raises(tmp_path: Path) -> None:
    fake_exe = tmp_path / "mtgo_bridge.exe"
    with pytest.raises(FileNotFoundError):
        mtgo_bridge_client.run_bridge_command("collection", bridge_path=str(fake_exe))


def test_resolve_bridge_from_env(monkeypatch, tmp_path: Path) -> None:
    fake_bridge = tmp_path / "mtgo_bridge.exe"
    fake_bridge.write_text("stub")
    monkeypatch.setenv("MTGO_BRIDGE_PATH", str(fake_bridge))
    resolved = mtgo_bridge_client._resolve_bridge_path(None)  # type: ignore[attr-defined]
    assert resolved == fake_bridge


# --- _sanitize_json_payload --------------------------------------------------


def test_sanitize_json_payload_parses_valid_json() -> None:
    payload = mtgo_bridge_client._sanitize_json_payload('{"a": 1, "b": [2, 3]}')
    assert payload == {"a": 1, "b": [2, 3]}


def test_sanitize_json_payload_strips_bom() -> None:
    # A leading UTF-8 BOM must be stripped before json.loads.
    payload = mtgo_bridge_client._sanitize_json_payload('﻿{"ok": true}')
    assert payload == {"ok": True}


def test_sanitize_json_payload_empty_raises() -> None:
    with pytest.raises(mtgo_bridge_client.BridgeCommandError, match="no output"):
        mtgo_bridge_client._sanitize_json_payload("   \n\t  ")


def test_sanitize_json_payload_invalid_json_raises() -> None:
    with pytest.raises(mtgo_bridge_client.BridgeCommandError, match="Invalid JSON payload"):
        mtgo_bridge_client._sanitize_json_payload("{not json}")


# --- _resolve_bridge_path branches -------------------------------------------


def test_resolve_bridge_env_missing_file_falls_back(monkeypatch, tmp_path: Path) -> None:
    # MTGO_BRIDGE_PATH set but the file does not exist: must fall through to
    # the default candidates. With no candidates available, returns None.
    missing = tmp_path / "does_not_exist.exe"
    monkeypatch.setenv("MTGO_BRIDGE_PATH", str(missing))
    monkeypatch.setattr(mtgo_bridge_client, "_default_bridge_candidates", lambda: [])
    assert mtgo_bridge_client._resolve_bridge_path(None) is None


def test_resolve_bridge_explicit_missing_returns_none(tmp_path: Path) -> None:
    missing = tmp_path / "nope.exe"
    assert mtgo_bridge_client._resolve_bridge_path(str(missing)) is None


# --- _command_worker error paths ---------------------------------------------


def _write_stub(tmp_path: Path, body: str) -> Path:
    """Write a small Python script invoked as ``python <script>``."""
    script = tmp_path / "stub.py"
    script.write_text(body)
    return script


def test_command_worker_nonzero_exit_surfaces_stderr(tmp_path: Path) -> None:
    import sys

    script = _write_stub(
        tmp_path,
        "import sys\nsys.stderr.write('boom detail')\nsys.exit(3)\n",
    )
    result_queue: queue_mod.Queue = queue_mod.Queue()
    mtgo_bridge_client._command_worker(sys.executable, [str(script)], result_queue)
    status, payload = result_queue.get_nowait()
    assert status == "error"
    assert "exited with code 3" in payload
    assert "boom detail" in payload


def test_command_worker_timeout_surfaces_message(tmp_path: Path) -> None:
    import sys

    script = _write_stub(tmp_path, "import time\ntime.sleep(5)\n")
    result_queue: queue_mod.Queue = queue_mod.Queue()
    mtgo_bridge_client._command_worker(sys.executable, [str(script)], result_queue, timeout=0.2)
    status, payload = result_queue.get_nowait()
    assert status == "error"
    assert "timed out after" in payload


def test_command_worker_success_serializes_payload(tmp_path: Path) -> None:
    import sys

    script = _write_stub(tmp_path, "import sys\nsys.stdout.write('{\"hi\": 1}')\n")
    result_queue: queue_mod.Queue = queue_mod.Queue()
    mtgo_bridge_client._command_worker(sys.executable, [str(script)], result_queue)
    status, payload = result_queue.get_nowait()
    assert status == "ok"
    assert payload == {"hi": 1}


# --- Executable-bridge stub helper -------------------------------------------


def _write_executable_bridge(tmp_path: Path, body: str) -> Path:
    """Create a directly-runnable ``bridge`` that delegates to a Python script.

    ``submit_bridge_command`` / ``BridgeWatcher`` invoke the resolved path as
    ``[bridge_path, *args]`` (no interpreter), so the stub must be executable on
    its own. We emit a Python program plus a thin OS-native launcher that calls
    the current interpreter, keeping the test cross-platform (Windows CI uses a
    ``.bat`` shim; POSIX uses a ``chmod +x`` shell shim).
    """
    program = tmp_path / "bridge_program.py"
    program.write_text(textwrap.dedent(body))

    if os.name == "nt":
        launcher = tmp_path / "bridge.bat"
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "{program}" %*\r\n')
        return launcher

    launcher = tmp_path / "bridge.sh"
    launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{program}" "$@"\n')
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return launcher


# --- BridgeCommandFuture -----------------------------------------------------


def _start_future(tmp_path: Path, body: str, timeout: float | None = None):
    """Run ``_command_worker`` against a Python stub inside a real process."""
    script = _write_stub(tmp_path, body)
    ctx = mp.get_context("spawn")
    result_queue: mp.Queue = ctx.Queue()
    process = ctx.Process(
        target=mtgo_bridge_client._command_worker,
        args=(sys.executable, [str(script)], result_queue, timeout),
    )
    process.start()
    return bridge_commands.BridgeCommandFuture(process, result_queue)


def test_future_result_returns_payload_on_ok(tmp_path: Path) -> None:
    future = _start_future(tmp_path, 'import sys\nsys.stdout.write(\'{"ok": true, "n": 5}\')\n')
    try:
        assert future.result(timeout=30) == {"ok": True, "n": 5}
    finally:
        future.cancel()


def test_future_result_raises_on_error_status(tmp_path: Path) -> None:
    future = _start_future(
        tmp_path,
        "import sys\nsys.stderr.write('kaput')\nsys.exit(2)\n",
    )
    try:
        with pytest.raises(bridge_commands.BridgeCommandError, match="exited with code 2"):
            future.result(timeout=30)
    finally:
        future.cancel()


def test_future_result_times_out_and_cancels_on_empty_queue() -> None:
    """An empty result queue makes ``result`` time out, raise, and tear down."""
    ctx = mp.get_context("spawn")
    empty_queue: mp.Queue = ctx.Queue()
    # A long-lived child whose teardown ``cancel()`` must guarantee.
    process = ctx.Process(target=_idle_forever)
    process.start()
    future = bridge_commands.BridgeCommandFuture(process, empty_queue)
    try:
        with pytest.raises(bridge_commands.BridgeCommandError, match="did not produce a result"):
            future.result(timeout=0.2)
        # result() calls cancel() on timeout, which terminates the process.
        process.join(10)
        assert not process.is_alive()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(5)


def _idle_forever() -> None:
    import time

    while True:
        time.sleep(0.1)


# --- _queue_replace ----------------------------------------------------------


def test_queue_replace_into_empty_queue() -> None:
    q: queue_mod.Queue = queue_mod.Queue(maxsize=1)
    bridge_watch._queue_replace(q, {"v": 1})
    assert q.get_nowait() == {"v": 1}


def test_queue_replace_overwrites_stale_item() -> None:
    q: queue_mod.Queue = queue_mod.Queue(maxsize=1)
    q.put_nowait({"v": 1})
    bridge_watch._queue_replace(q, {"v": 2})
    assert q.get_nowait() == {"v": 2}
    assert q.empty()


# --- _watch_worker (real subprocess streaming parser) ------------------------


def _run_watch_to_completion(bridge: Path, *, max_iterations: int = 300) -> list:
    """Drive ``_watch_worker`` against ``bridge`` and collect emitted payloads.

    Uses a real ``maxsize=1`` queue (production semantics: only the latest
    snapshot is retained), draining as items arrive until the worker exits.
    """
    ctx = mp.get_context("spawn")
    out_queue: mp.Queue = ctx.Queue(maxsize=1)
    stop_event = ctx.Event()
    process = ctx.Process(
        target=bridge_watch._watch_worker,
        args=(str(bridge), out_queue, stop_event),
    )
    process.start()

    seen: list = []
    iterations = max_iterations
    while iterations > 0 and (process.is_alive() or not out_queue.empty()):
        try:
            seen.append(out_queue.get(timeout=0.1))
        except queue_mod.Empty:
            pass
        iterations -= 1

    stop_event.set()
    process.join(10)
    if process.is_alive():
        process.terminate()
        process.join(5)
    return seen


def test_watch_worker_strips_bom_and_skips_malformed(tmp_path: Path) -> None:
    """A BOM-prefixed object parses; an interleaved malformed line is skipped."""
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import sys, time
        sys.stdout.write('this is not json\n')
        sys.stdout.flush()
        time.sleep(0.2)
        sys.stdout.write('﻿{"timer": 1}\n')
        sys.stdout.flush()
        """,
    )
    seen = _run_watch_to_completion(bridge)
    assert {"timer": 1} in seen
    # The malformed line must never have produced a payload.
    assert "this is not json" not in seen
    assert {} not in seen


def test_watch_worker_parses_multiline_object(tmp_path: Path) -> None:
    """The bracket-depth parser reassembles an object spanning several reads."""
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import sys
        sys.stdout.write('{\n')
        sys.stdout.write('  "timer": 2,\n')
        sys.stdout.write('  "opponent": "alice"\n')
        sys.stdout.write('}\n')
        sys.stdout.flush()
        """,
    )
    seen = _run_watch_to_completion(bridge)
    assert {"timer": 2, "opponent": "alice"} in seen


# --- BridgeWatcher lifecycle -------------------------------------------------


def test_bridge_watcher_streams_then_stops(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import sys, time
        sys.stdout.write('{"timer": 42}\n')
        sys.stdout.flush()
        # Stay alive so the parent exercises stop()/teardown explicitly.
        time.sleep(30)
        """,
    )
    with bridge_watch.BridgeWatcher(bridge_path=bridge) as watcher:
        payload = watcher.latest(block=True, timeout=20)
        assert payload == {"timer": 42}
        process = watcher._process
        assert process is not None and process.is_alive()
    # __exit__ -> stop() must have terminated the background process.
    process.join(10)
    assert not process.is_alive()


def test_bridge_watcher_latest_nonblocking_empty_returns_none(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        "import time\ntime.sleep(30)\n",
    )
    watcher = bridge_watch.BridgeWatcher(bridge_path=bridge)
    watcher.start()
    try:
        assert watcher.latest(block=False) is None
    finally:
        watcher.stop()


# --- Convenience entry points (argv contract) --------------------------------


def test_fetch_collection_snapshot_invokes_collection_mode(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import json, sys
        print(json.dumps({"mode": sys.argv[1], "argv": sys.argv[1:]}))
        """,
    )
    payload = mtgo_bridge_client.fetch_collection_snapshot(bridge_path=str(bridge), timeout=30)
    assert payload == {"mode": "collection", "argv": ["collection"]}


def test_fetch_match_history_invokes_history_mode(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import json, sys
        print(json.dumps({"argv": sys.argv[1:]}))
        """,
    )
    payload = mtgo_bridge_client.fetch_match_history(bridge_path=str(bridge), timeout=30)
    assert payload == {"argv": ["history"]}


def test_fetch_trade_snapshot_passes_status_subcommand(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import json, sys
        print(json.dumps({"argv": sys.argv[1:]}))
        """,
    )
    payload = mtgo_bridge_client.fetch_trade_snapshot(bridge_path=str(bridge), timeout=30)
    assert payload == {"argv": ["trade", "status"]}


def test_accept_trade_passes_accept_subcommand(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import json, sys
        print(json.dumps({"argv": sys.argv[1:]}))
        """,
    )
    payload = mtgo_bridge_client.accept_trade(bridge_path=str(bridge), timeout=30)
    assert payload == {"argv": ["trade", "accept"]}


def test_run_bridge_command_passes_extra_args(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import json, sys
        print(json.dumps({"argv": sys.argv[1:]}))
        """,
    )
    payload = mtgo_bridge_client.run_bridge_command(
        "all", bridge_path=str(bridge), extra_args=("--verbose",), timeout=30
    )
    assert payload == {"argv": ["all", "--verbose"]}


def test_async_entry_point_returns_future_resolving_payload(tmp_path: Path) -> None:
    bridge = _write_executable_bridge(
        tmp_path,
        r"""
        import json, sys
        print(json.dumps({"argv": sys.argv[1:]}))
        """,
    )
    future = mtgo_bridge_client.fetch_collection_snapshot_async(bridge_path=str(bridge))
    try:
        assert future.result(timeout=30) == {"argv": ["collection"]}
    finally:
        future.cancel()
