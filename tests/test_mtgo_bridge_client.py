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
