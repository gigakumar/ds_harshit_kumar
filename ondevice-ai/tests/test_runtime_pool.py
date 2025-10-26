import subprocess
from pathlib import Path
from typing import Any

import pytest

from core.runtime_gateway import RuntimeGateway
from core.runtime_pool import PoolConfig, RuntimePool


class DummyPopen:
    _pid_counter = 1200

    def __init__(self, cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
        self.cmd = cmd
        self.cwd = cwd
        self.env = env or {}
        self.pid = DummyPopen._pid_counter
        DummyPopen._pid_counter += 1
        self._alive = True

    def poll(self) -> Any:
        return None if self._alive else 0

    def terminate(self) -> None:
        self._alive = False

    def kill(self) -> None:
        self._alive = False

    def wait(self, timeout: float | None = None) -> int:  # noqa: ARG002 - parity with subprocess.Popen
        self._alive = False
        return 0


@pytest.fixture
def fake_popen(monkeypatch: pytest.MonkeyPatch) -> list[DummyPopen]:
    instances: list[DummyPopen] = []

    def factory(cmd: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> DummyPopen:
        proc = DummyPopen(cmd, cwd, env)
        instances.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", factory)
    return instances


def test_spawn_registers_gateway_endpoint(fake_popen: list[DummyPopen]) -> None:
    gateway = RuntimeGateway()
    pool = RuntimePool(Path("worker.py"), gateway, PoolConfig(min_runtimes=0, max_runtimes=2))

    proc = pool.spawn(name="worker-1")
    endpoint = gateway.find("http", "worker-1")
    assert endpoint is not None
    assert endpoint.metadata["status"] == "booting"
    assert proc.env["RUNTIME_PORT"].isdigit()

    pool.heartbeat()
    endpoint = gateway.find("http", "worker-1")
    assert endpoint is not None and endpoint.metadata["status"] == "ready"

    assert pool.remove("worker-1")
    assert gateway.find("http", "worker-1") is None
    pool.stop()


def test_heartbeat_restarts_crashed_process(fake_popen: list[DummyPopen]) -> None:
    gateway = RuntimeGateway()
    pool = RuntimePool(Path("worker.py"), gateway, PoolConfig(min_runtimes=0, restart_backoff=0.0))

    proc = pool.spawn(name="worker-main")
    assert proc.restarts == 0

    # Simulate crash.
    fake_popen[0]._alive = False
    pool.heartbeat()

    assert len(fake_popen) >= 2
    workers = {worker["name"]: worker for worker in pool.snapshot()["workers"]}
    new_proc = workers["worker-main"]
    assert new_proc["restarts"] == 1
    endpoint = gateway.find("http", "worker-main")
    assert endpoint is not None and endpoint.metadata["restarts"] == 1

    pool.stop()


def test_scale_to_adjusts_capacity(fake_popen: list[DummyPopen]) -> None:
    gateway = RuntimeGateway()
    pool = RuntimePool(Path("worker.py"), gateway, PoolConfig(min_runtimes=0, max_runtimes=3))

    pool.scale_to(2)
    workers = {worker["name"] for worker in pool.snapshot()["workers"]}
    assert workers == {"runtime-1", "runtime-2"}

    pool.scale_to(1)
    workers = {worker["name"] for worker in pool.snapshot()["workers"]}
    assert workers == {"runtime-1"}
    assert gateway.find("http", "runtime-2") is None

    pool.stop()


def test_heartbeat_records_metrics(fake_popen: list[DummyPopen]) -> None:
    gateway = RuntimeGateway()
    pool = RuntimePool(Path("worker.py"), gateway, PoolConfig(min_runtimes=0))

    pool.scale_to(1)
    pool.heartbeat()

    metrics = pool.inspect()["metrics"]
    assert metrics, "Expected heartbeat to record metrics entry"
    latest = metrics[0]
    assert latest["summary"]["alive"] == 1
    worker_metrics = latest["workers"]["runtime-1"]
    assert "cpu_percent" in worker_metrics
    assert "memory_rss" in worker_metrics

    pool.stop()