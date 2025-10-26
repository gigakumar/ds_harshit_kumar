from __future__ import annotations

import io
import json
import os
import types
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from cli import index as cli_index


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    return tmp_path / "state"


def _make_status(**kwargs: Any) -> Any:
    status = types.SimpleNamespace(
        running=kwargs.get("running", False),
        pid=kwargs.get("pid"),
        created_at=kwargs.get("created_at"),
        cmd=kwargs.get("cmd"),
        uptime_seconds=kwargs.get("uptime_seconds"),
        message=kwargs.get("message", ""),
        health_status=kwargs.get("health_status"),
        health_url=kwargs.get("health_url"),
    )
    return status


def test_daemon_status_command(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_status = _make_status(running=True, pid=1234, uptime_seconds=42, message="Daemon is running.")
    monkeypatch.setattr(cli_index, "_daemon_status", lambda: fake_status)

    parser = cli_index.build_parser()
    args = parser.parse_args(["daemon", "status"])

    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    args.func(args)
    output = buffer.getvalue().strip()
    assert "Daemon is running" in output
    assert "pid=1234" in output


def test_daemon_start_passes_arguments(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_args = {}

    def fake_start(*, args=None, env=None, state_dir=None, python_executable=None, wait=mock.ANY):  # type: ignore[no-untyped-def]
        captured_args.update({
            "args": args,
            "env": env,
        })
        return _make_status(running=True, pid=2222, message="Daemon is running.")

    monkeypatch.setattr(cli_index, "_start_daemon", fake_start)

    parser = cli_index.build_parser()
    args = parser.parse_args([
        "daemon",
        "start",
        "--grpc-port",
        "50060",
        "--mlx-port",
        "9100",
        "--config",
        "/tmp/config.yaml",
    ])

    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    args.func(args)

    assert captured_args["args"] == ["--grpc-port", "50060", "--mlx-port", "9100"]
    assert captured_args["env"] == {"MAHI_CONFIG": "/tmp/config.yaml"}


def test_daemon_start_with_config_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_args = {}

    def fake_start(*, args=None, env=None, state_dir=None, python_executable=None, wait=mock.ANY):  # type: ignore[no-untyped-def]
        captured_args.update({
            "env": env,
        })
        return _make_status(running=True, pid=4444, message="Daemon is running.")

    monkeypatch.setattr(cli_index, "_start_daemon", fake_start)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")

    parser = cli_index.build_parser()
    args = parser.parse_args([
        "daemon",
        "start",
        "--config",
        "/tmp/config.yaml",
        "--set",
        "model.backend=ollama",
        "--set",
        "runtime_pool.enabled=true",
        "--secret",
        "model.openai.api_key=OPENAI_API_KEY",
    ])

    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    args.func(args)

    env = captured_args["env"]
    assert env is not None
    assert env["MAHI_CONFIG"] == "/tmp/config.yaml"
    overrides = json.loads(env["MAHI_CONFIG_OVERRIDES"])
    assert overrides["model"]["backend"] == "ollama"
    assert overrides["runtime_pool"]["enabled"] is True
    secret_overrides = json.loads(env["MAHI_SECRET_OVERRIDES"])
    assert secret_overrides["model"]["openai"]["api_key"] == "sk-test-123"


def test_daemon_stop(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_stop(*, state_dir=None, timeout=mock.ANY):  # type: ignore[no-untyped-def]
        captured.update({"state_dir": state_dir, "timeout": timeout})
        return _make_status(message="Daemon stopped.")

    monkeypatch.setattr(cli_index, "_stop_daemon", fake_stop)

    parser = cli_index.build_parser()
    args = parser.parse_args(["daemon", "stop"])

    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    args.func(args)

    assert captured["timeout"] == mock.ANY
    assert "Daemon stopped" in buffer.getvalue()


def test_daemon_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    captured_args = {}

    def fake_restart(*, args=None, env=None, state_dir=None, python_executable=None, wait=mock.ANY):  # type: ignore[no-untyped-def]
        captured_args.update({"args": args, "env": env})
        return _make_status(running=True, pid=3333, message="Restarted.")

    monkeypatch.setattr(cli_index, "_restart_daemon", fake_restart)

    parser = cli_index.build_parser()
    args = parser.parse_args([
        "daemon",
        "restart",
        "--grpc-host",
        "127.0.0.1",
        "--models-dir",
        "./models",
    ])

    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    args.func(args)

    assert captured_args["args"] == ["--grpc-host", "127.0.0.1", "--models-dir", "./models"]
    assert captured_args["env"] is None
    assert "Restarted" in buffer.getvalue()


def test_diagnostics_cli_invokes_bundle(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_bundle(*, output_path=None, include_logs=True, include_config=True, include_plugins=True, include_state_listing=True):  # type: ignore[no-untyped-def]
        captured.update({
            "output_path": output_path,
            "include_logs": include_logs,
            "include_config": include_config,
            "include_plugins": include_plugins,
            "include_state_listing": include_state_listing,
        })
        return Path("/tmp/fake-bundle.zip")

    monkeypatch.setattr(cli_index, "create_diagnostics_bundle", fake_bundle)

    parser = cli_index.build_parser()
    args = parser.parse_args([
        "diagnostics",
        "--output",
        "./diag.zip",
        "--no-logs",
        "--no-plugins",
    ])

    buffer = io.StringIO()
    monkeypatch.setattr("sys.stdout", buffer)
    args.func(args)

    assert captured["output_path"] == "./diag.zip"
    assert captured["include_logs"] is False
    assert captured["include_config"] is True
    assert captured["include_plugins"] is False
    assert captured["include_state_listing"] is True
    assert buffer.getvalue().strip() == "/tmp/fake-bundle.zip"
