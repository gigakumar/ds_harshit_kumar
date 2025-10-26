from __future__ import annotations

import json
from textwrap import dedent

import pytest
import yaml

from core import config


def test_env_override_applies(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    cfg_path = tmp_path / "automation.yaml"
    cfg_path.write_text(dedent(
        """
        model:
          backend: mlx
        permissions:
          file_access: false
          calendar_access: false
          mail_access: false
        """
    ))
    monkeypatch.setenv("MAHI_CONFIG", str(cfg_path))
    monkeypatch.setenv("MAHI_CFG__MODEL__BACKEND", "ollama")
    monkeypatch.setenv("MAHI_CFG__PERMISSIONS__FILE_ACCESS", "true")

    data = config.get_config()
    assert data["model"]["backend"] == "ollama"
    assert data["permissions"]["file_access"] is True


def test_json_override_payload(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    cfg_path = tmp_path / "automation.yaml"
    cfg_path.write_text("model:\n  backend: mlx\n")
    monkeypatch.setenv("MAHI_CONFIG", str(cfg_path))
    monkeypatch.setenv(
        "MAHI_CONFIG_OVERRIDES",
        json.dumps({
            "permissions": {"file_access": True},
            "runtime_pool": {"enabled": False},
        }),
    )

    data = config.get_config()
    assert data["permissions"]["file_access"] is True
    assert data["runtime_pool"]["enabled"] is False


def test_secret_override_not_persisted(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    cfg_path = tmp_path / "automation.yaml"
    cfg_path.write_text(dedent(
        """
        model:
          openai:
            api_key: ''
        """
    ))
    monkeypatch.setenv("MAHI_CONFIG", str(cfg_path))
    monkeypatch.setenv("MAHI_SECRET__MODEL__OPENAI__API_KEY", "sk-secret")

    data = config.get_config()
    assert data["model"]["openai"]["api_key"] == "sk-secret"

    config.save_config(data)

    rendered = cfg_path.read_text()
    assert "sk-secret" not in rendered
    loaded = yaml.safe_load(rendered) or {}
    api_key = loaded.get("model", {}).get("openai", {}).get("api_key")
    assert api_key in (None, "")