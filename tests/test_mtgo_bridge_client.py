import queue as queue_mod
from pathlib import Path

import pytest

from services.mtgo_bridge_service import client as mtgo_bridge_client


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
