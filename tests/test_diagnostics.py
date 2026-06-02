"""Tests for diagnostics: EventLogger and export_diagnostics_bundle."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from utils.diagnostics import EventLogger, _get_app_version, export_diagnostics_bundle

# ---------------------------------------------------------------------------
# EventLogger
# ---------------------------------------------------------------------------


class TestEventLogger:
    def test_disabled_by_default(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path)
        assert el.enabled is False

    def test_enabled_flag_roundtrip(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path, enabled=True)
        assert el.enabled is True
        el.enabled = False
        assert el.enabled is False

    def test_no_file_when_disabled(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path, enabled=False)
        el.log("test_event")
        assert not el.path.exists()

    def test_event_written_when_enabled(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path, enabled=True)
        el.log("deck_loaded", {"format": "Modern"})
        assert el.path.exists()

    def test_event_jsonl_format(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path, enabled=True)
        el.log("archetype_selected", {"name": "UR Murktide"})

        lines = el.path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event"] == "archetype_selected"
        assert record["data"] == {"name": "UR Murktide"}
        assert record["ts"].endswith("Z")

    def test_multiple_events_appended(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path, enabled=True)
        el.log("event_a")
        el.log("event_b")
        el.log("event_c")

        lines = el.path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        events = [json.loads(line)["event"] for line in lines]
        assert events == ["event_a", "event_b", "event_c"]

    def test_event_without_data(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path, enabled=True)
        el.log("simple_event")

        record = json.loads(el.path.read_text(encoding="utf-8").strip())
        assert "data" not in record

    def test_rotation_renames_file(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path, enabled=True)
        # Override max size to trigger rotation immediately
        el._MAX_BYTES = 1
        el.log("first_event")  # writes file; next call sees size >= 1
        el.log("second_event")  # triggers rotation

        rotated = tmp_path / "events.jsonl.1"
        assert rotated.exists()
        # New events.jsonl should only contain the second event
        content = el.path.read_text(encoding="utf-8").strip()
        assert json.loads(content)["event"] == "second_event"

    def test_path_property(self, tmp_path: Path) -> None:
        el = EventLogger(tmp_path)
        assert el.path == tmp_path / "events.jsonl"

    def test_write_failure_is_non_fatal(self, tmp_path: Path) -> None:
        """An I/O error while writing must be swallowed, never raised."""
        # A regular file sitting where the logs directory should be makes
        # ``mkdir`` (and thus the whole write) fail with an OSError.
        blocker = tmp_path / "logs"
        blocker.write_text("not a directory")
        el = EventLogger(blocker / "nested", enabled=True)

        el.log("boom")  # must not raise

        assert not el.path.exists()


# ---------------------------------------------------------------------------
# export_diagnostics_bundle
# ---------------------------------------------------------------------------


class TestExportDiagnosticsBundle:
    def _make_logs(self, logs_dir: Path) -> None:
        (logs_dir / "mtgo_tools_20250101_120000.log").write_text("INFO log line 1\nINFO log line 2")
        (logs_dir / "mtgo_tools_20250102_120000.log").write_text("INFO log line 3")

    def test_creates_zip(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        self._make_logs(logs_dir)

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)
        assert out.exists()
        assert zipfile.is_zipfile(out)

    def test_zip_contains_system_info(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)
        with zipfile.ZipFile(out) as zf:
            assert "system_info.json" in zf.namelist()
            info = json.loads(zf.read("system_info.json"))
            assert "platform" in info
            assert "platform_release" in info
            assert "python_version" in info
            # app_version must always be present and non-empty for support triage
            assert "app_version" in info
            assert info["app_version"]

    def test_event_log_rotated_files_included(self, tmp_path: Path) -> None:
        """Rotated event files (events.jsonl.1) must also land in the bundle."""
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        el = EventLogger(logs_dir, enabled=True)
        # Force rotation: first write creates the file, second sees size >= 1
        el._MAX_BYTES = 1
        el.log("first_event")
        el.log("second_event")
        assert (logs_dir / "events.jsonl.1").exists()

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert "logs/events.jsonl" in names
        assert "logs/events.jsonl.1" in names

    def test_log_files_included(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        self._make_logs(logs_dir)

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
        assert "logs/mtgo_tools_20250101_120000.log" in names
        assert "logs/mtgo_tools_20250102_120000.log" in names

    def test_notes_included_when_provided(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        out = export_diagnostics_bundle(
            tmp_path / "bundle.zip", logs_dir=logs_dir, notes="Bug: crash on load"
        )
        with zipfile.ZipFile(out) as zf:
            assert "notes.txt" in zf.namelist()
            assert zf.read("notes.txt").decode() == "Bug: crash on load"

    def test_notes_omitted_when_empty(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir, notes="   ")
        with zipfile.ZipFile(out) as zf:
            assert "notes.txt" not in zf.namelist()

    def test_event_log_included_by_default(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        el = EventLogger(logs_dir, enabled=True)
        el.log("test_event")

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)
        with zipfile.ZipFile(out) as zf:
            assert "logs/events.jsonl" in zf.namelist()

    def test_event_log_excluded_when_opted_out(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()
        el = EventLogger(logs_dir, enabled=True)
        el.log("test_event")

        out = export_diagnostics_bundle(
            tmp_path / "bundle.zip", logs_dir=logs_dir, include_events=False
        )
        with zipfile.ZipFile(out) as zf:
            assert not any(n.startswith("logs/events") for n in zf.namelist())

    def test_empty_logs_dir_produces_valid_zip(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)
        assert zipfile.is_zipfile(out)

    def test_missing_logs_dir_produces_valid_zip(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "nonexistent_logs"

        out = export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)
        assert zipfile.is_zipfile(out)

    def test_output_extension_normalised_to_zip(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        out = export_diagnostics_bundle(tmp_path / "bundle", logs_dir=logs_dir)
        assert out.suffix == ".zip"
        assert out.exists()

    def test_returns_output_path(self, tmp_path: Path) -> None:
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        dest = tmp_path / "diag.zip"
        result = export_diagnostics_bundle(dest, logs_dir=logs_dir)
        assert result == dest

    def test_no_network_calls(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bundle export must never open a network socket."""
        import socket

        def forbid_connect(self, *args, **kwargs):  # type: ignore[override]
            raise AssertionError("export_diagnostics_bundle must not make network calls")

        monkeypatch.setattr(socket.socket, "connect", forbid_connect)
        logs_dir = tmp_path / "logs"
        logs_dir.mkdir()

        # Should not raise. ``monkeypatch`` restores ``connect`` automatically.
        export_diagnostics_bundle(tmp_path / "bundle.zip", logs_dir=logs_dir)


# ---------------------------------------------------------------------------
# _get_app_version fallback chain
# ---------------------------------------------------------------------------


class TestGetAppVersion:
    def test_returns_non_empty_string(self) -> None:
        assert isinstance(_get_app_version(), str)
        assert _get_app_version()

    def test_falls_back_to_constants_app_version(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When package metadata is unavailable, use utils.constants.APP_VERSION."""
        import importlib.metadata
        import sys
        import types

        def raise_metadata(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise importlib.metadata.PackageNotFoundError("mtgo_tools")

        monkeypatch.setattr(importlib.metadata, "version", raise_metadata)
        # Inject a lightweight stand-in so the import succeeds without pulling in
        # the real utils.constants package (which imports wx).
        fake = types.ModuleType("utils.constants")
        fake.APP_VERSION = "9.9.9"  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "utils.constants", fake)

        assert _get_app_version() == "9.9.9"

    def test_falls_through_to_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If both metadata and constants lookups fail, fall back to 'unknown'."""
        import importlib.metadata

        def raise_metadata(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise importlib.metadata.PackageNotFoundError("mtgo_tools")

        monkeypatch.setattr(importlib.metadata, "version", raise_metadata)
        # Block the utils.constants fallback so we reach the final "unknown".
        import builtins

        original_import = builtins.__import__

        def blocked_import(name, *args, **kwargs):  # type: ignore[no-untyped-def]
            if name == "utils.constants":
                raise ImportError("blocked for test")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", blocked_import)
        assert _get_app_version() == "unknown"
