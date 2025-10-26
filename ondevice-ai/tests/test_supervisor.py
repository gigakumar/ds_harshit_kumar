from __future__ import annotations

import json
import sys
import textwrap
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from core.supervisor import Supervisor, SupervisorConfig, SupervisorHooks


@pytest.fixture()
def temp_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "log": tmp_path / "supervisor.log",
        "state": tmp_path / "supervisor_state.json",
        "scratch": tmp_path / "attempt.txt",
    }


def test_supervisor_restarts_then_succeeds(temp_paths: dict[str, Path]) -> None:
    script = textwrap.dedent(
        f"""
        import sys, time, pathlib
        counter_path = pathlib.Path(r"{temp_paths['scratch']}")
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        time.sleep(0.05)
        sys.exit(0 if count >= 1 else 1)
        """
    )
    command = [sys.executable, "-c", script]
    config = SupervisorConfig(
        max_restarts=3,
        window_seconds=5.0,
        backoff_seconds=0.01,
        max_backoff_seconds=0.05,
    )
    supervisor = Supervisor(
        command,
        log_path=temp_paths["log"],
        state_file=temp_paths["state"],
        config=config,
        register_signals=False,
    )
    exit_code = supervisor.run()

    assert exit_code == 0
    state = json.loads(temp_paths["state"].read_text(encoding="utf-8"))
    assert state["restart_count"] >= 1
    assert state["last_exit_code"] == 0
    assert state["child_pid"] is None


def test_supervisor_respects_restart_budget(temp_paths: dict[str, Path]) -> None:
    script = "import sys, time; time.sleep(0.02); sys.exit(1)"
    command = [sys.executable, "-c", script]
    config = SupervisorConfig(
        max_restarts=2,
        window_seconds=1.0,
        backoff_seconds=0.01,
        max_backoff_seconds=0.05,
    )
    supervisor = Supervisor(
        command,
        log_path=temp_paths["log"],
        state_file=temp_paths["state"],
        config=config,
        register_signals=False,
    )
    exit_code = supervisor.run()

    assert exit_code == 1
    state = json.loads(temp_paths["state"].read_text(encoding="utf-8"))
    assert state["restart_count"] == 2
    assert state["last_exit_code"] == 1


def test_supervisor_health_probe_reports_running(temp_paths: dict[str, Path]) -> None:
    script = "import time; time.sleep(0.3)"
    command = [sys.executable, "-c", script]
    config = SupervisorConfig(
        max_restarts=1,
        window_seconds=5.0,
        backoff_seconds=0.01,
        max_backoff_seconds=0.05,
        health_port=0,
    )
    supervisor = Supervisor(
        command,
        log_path=temp_paths["log"],
        state_file=temp_paths["state"],
        config=config,
        register_signals=False,
    )

    thread = threading.Thread(target=supervisor.run, daemon=True)
    thread.start()

    assert supervisor.wait_for_health(timeout=2.0)
    endpoint = supervisor.health_endpoint
    assert endpoint is not None
    url = f"http://{endpoint[0]}:{endpoint[1]}/healthz"

    payload: dict[str, object] | None = None
    deadline = time.time() + 5.0
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                status_code = resp.status
        except urllib.error.HTTPError as exc:
            status_code = exc.code
            if status_code not in {200, 503}:
                raise
        except urllib.error.URLError:
            status_code = None
        if status_code == 200 and payload is not None:
            break
        time.sleep(0.05)

    assert payload is not None
    assert payload["running"] is True
    assert payload["status"] == "ready"

    supervisor.stop()
    thread.join(timeout=5.0)

    state = json.loads(temp_paths["state"].read_text(encoding="utf-8"))
    assert state["health"]["status"] in {"stopped", "failed"}


def test_supervisor_hooks_invoked(temp_paths: dict[str, Path]) -> None:
    events: list[tuple[str, int | None]] = []

    hooks = SupervisorHooks(
        on_child_start=lambda pid, restarts: events.append(("start", restarts)),
        on_child_exit=lambda code, restarts: events.append(("exit", code)),
        on_restart=lambda count: events.append(("restart", count)),
    )

    script = textwrap.dedent(
        f"""
        import sys, pathlib, time
        counter_path = pathlib.Path(r"{temp_paths['scratch']}")
        count = int(counter_path.read_text()) if counter_path.exists() else 0
        counter_path.write_text(str(count + 1))
        time.sleep(0.05)
        sys.exit(0 if count >= 1 else 1)
        """
    )
    command = [sys.executable, "-c", script]
    config = SupervisorConfig(max_restarts=3, window_seconds=5.0, backoff_seconds=0.01, max_backoff_seconds=0.05)
    supervisor = Supervisor(
        command,
        log_path=temp_paths["log"],
        state_file=temp_paths["state"],
        config=config,
        hooks=hooks,
    )
    exit_code = supervisor.run()

    assert exit_code == 0
    assert ("restart", 1) in events
    start_events = [value for event, value in events if event == "start"]
    assert start_events[0] == 0
    assert 1 in start_events
    exit_events = [value for event, value in events if event == "exit"]
    assert exit_events[-1] == 0