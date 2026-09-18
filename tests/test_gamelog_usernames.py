"""Tests for the MTGO bridge username lookup in services.gamelog_service.usernames.

The bridge exits 0 and prints ``{"error": ...}`` when it cannot reach the client,
so a missing ``username`` key is a real failure rather than a quiet "no user".
These tests pin that every failure mode is both handled and logged.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

import pytest

from services.gamelog_service import usernames as usernames_mod


class _Completed:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def captured_logs(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Collect (level, message) pairs emitted by the module's logger."""
    records: list[tuple[str, str]] = []

    def _record(level: str):
        def _log(msg: str, *args: Any, **kwargs: Any) -> None:
            try:
                records.append((level, msg.format(*args, **kwargs)))
            except (IndexError, KeyError):
                records.append((level, msg))

        return _log

    for level in ("debug", "info", "warning", "error"):
        monkeypatch.setattr(usernames_mod.logger, level, _record(level))
    return records


def _patch_run(monkeypatch: pytest.MonkeyPatch, result: Any) -> dict[str, Any]:
    """Patch subprocess.run; return a dict capturing the kwargs it was called with."""
    seen: dict[str, Any] = {}

    def _fake_run(cmd: Any, **kwargs: Any) -> Any:
        seen["cmd"] = cmd
        seen.update(kwargs)
        if isinstance(result, BaseException):
            raise result
        return result

    monkeypatch.setattr(usernames_mod.subprocess, "run", _fake_run)
    return seen


def test_returns_username_on_success(monkeypatch, captured_logs):
    _patch_run(monkeypatch, _Completed(stdout=json.dumps({"username": "pedrogush"})))
    assert usernames_mod.get_current_username() == "pedrogush"
    assert not [m for lvl, m in captured_logs if lvl == "warning"]


def test_missing_username_key_logs_bridge_error(monkeypatch, captured_logs):
    """The regression: exit 0 + valid JSON + no username key returned None silently."""
    _patch_run(monkeypatch, _Completed(stdout=json.dumps({"error": "MTGO client is not running"})))

    assert usernames_mod.get_current_username() is None

    warnings = [m for lvl, m in captured_logs if lvl == "warning"]
    assert len(warnings) == 1
    # The bridge's own diagnosis must reach the log, not be swallowed.
    assert "MTGO client is not running" in warnings[0]


def test_null_username_still_reports_error(monkeypatch, captured_logs):
    """The bridge now always emits the key, so null + error must still warn."""
    _patch_run(
        monkeypatch,
        _Completed(stdout=json.dumps({"username": None, "error": "TypeInitializationException: x"})),
    )
    assert usernames_mod.get_current_username() is None
    assert any("TypeInitializationException" in m for lvl, m in captured_logs if lvl == "warning")


def test_nonzero_exit_logs_stderr(monkeypatch, captured_logs):
    _patch_run(monkeypatch, _Completed(returncode=3, stderr="boom"))
    assert usernames_mod.get_current_username() is None
    assert any("exited 3" in m and "boom" in m for lvl, m in captured_logs if lvl == "warning")


def test_non_json_output_logs_warning(monkeypatch, captured_logs):
    _patch_run(monkeypatch, _Completed(stdout="not json at all"))
    assert usernames_mod.get_current_username() is None
    assert any("non-JSON" in m for lvl, m in captured_logs if lvl == "warning")


def test_timeout_is_reported_distinctly(monkeypatch, captured_logs):
    _patch_run(monkeypatch, subprocess.TimeoutExpired(cmd="MTGOBridge.exe", timeout=25.0))
    assert usernames_mod.get_current_username() is None
    assert any("timed out" in m for lvl, m in captured_logs if lvl == "warning")


def test_missing_executable_is_reported_distinctly(monkeypatch, captured_logs):
    _patch_run(monkeypatch, FileNotFoundError("MTGOBridge.exe not found"))
    assert usernames_mod.get_current_username() is None
    assert any("Could not run" in m for lvl, m in captured_logs if lvl == "warning")


def test_decodes_utf8_explicitly(monkeypatch):
    """text=True alone uses the Windows locale codec and breaks on non-ASCII names."""
    seen = _patch_run(monkeypatch, _Completed(stdout=json.dumps({"username": "Pedrão"})))

    assert usernames_mod.get_current_username() == "Pedrão"
    assert seen["encoding"] == "utf-8"
    assert seen["errors"] == "replace"


def test_timeout_has_headroom_over_measured_latency(monkeypatch):
    """Measured ~4.4s under load; the old hardcoded 10s was thin."""
    seen = _patch_run(monkeypatch, _Completed(stdout=json.dumps({"username": "x"})))
    usernames_mod.get_current_username()
    assert seen["timeout"] >= 20.0
