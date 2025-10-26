from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from core import diagnostics


@pytest.fixture
def temp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, Path]:
    config_path = tmp_path / "automation.yaml"
    config_path.write_text("permissions:\n  file_access: true\n", encoding="utf-8")

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    log_path = state_dir / "daemon.log"
    log_path.write_text("[daemon] test log", encoding="utf-8")

    monkeypatch.setenv("MAHI_CONFIG", str(config_path))
    monkeypatch.setenv("MAHI_STATE_DIR", str(state_dir))

    return {"config": config_path, "state": state_dir, "log": log_path}


def test_create_diagnostics_bundle_includes_artifacts(temp_env: dict[str, Path]) -> None:
    bundle_path = diagnostics.create_diagnostics_bundle(include_plugins=False)
    assert bundle_path.exists()

    with zipfile.ZipFile(bundle_path, "r") as bundle:
        names = set(bundle.namelist())
        assert "summary.json" in names
        assert "config/automation.yaml" in names
        assert "logs/daemon.log" in names
        assert "state.json" in names

        summary = json.loads(bundle.read("summary.json"))
        assert "daemon" in summary
        assert summary["environment"].get("MAHI_STATE_DIR") == str(temp_env["state"])

        state_listing = json.loads(bundle.read("state.json"))
        assert any(entry["path"] == "daemon.log" for entry in state_listing["files"])


def test_create_diagnostics_bundle_respects_flags(temp_env: dict[str, Path]) -> None:  # noqa: ARG001
    bundle_path = diagnostics.create_diagnostics_bundle(include_logs=False, include_state_listing=False, include_plugins=False)
    with zipfile.ZipFile(bundle_path, "r") as bundle:
        names = set(bundle.namelist())
        assert "logs/daemon.log" not in names
        assert "state.json" not in names
        assert "config/automation.yaml" in names