"""Manage worker runtime processes for serving automation tasks."""
from __future__ import annotations

import contextlib
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Deque, Dict, Optional

from core.runtime_gateway import RuntimeEndpoint, RuntimeGateway

try:  # pragma: no cover - optional dependency for rich process metrics
    import psutil  # type: ignore[import-not-found]
except Exception:  # pragma: no cover - psutil not installed
    psutil = None  # type: ignore[assignment]


@dataclass(slots=True)
class RuntimeProcess:
    """Book-keeping for a managed runtime worker."""

    name: str
    command: list[str]
    cwd: Path
    env: dict[str, str]
    port: int
    process: subprocess.Popen[Any]
    started_at: float
    restarts: int = 0
    last_health: dict[str, Any] | None = None

    def is_alive(self) -> bool:
        return self.process.poll() is None

    def terminate(self) -> None:
        if self.is_alive():
            with contextlib.suppress(Exception):
                self.process.terminate()

    def kill(self) -> None:
        if self.is_alive():
            with contextlib.suppress(Exception):
                self.process.kill()


@dataclass(slots=True)
class PoolConfig:
    min_runtimes: int = 0
    max_runtimes: int = 2
    desired_runtimes: Optional[int] = None
    base_port: int = 9600
    heartbeat_interval: float = 5.0
    restart_backoff: float = 3.0
    shutdown_timeout: float = 5.0


class RuntimePool:
    """Coordinate automation daemon worker processes."""

    def __init__(
        self,
        executable: Path,
        gateway: RuntimeGateway,
        config: PoolConfig | None = None,
        *,
        on_spawn: Optional[Callable[[RuntimeProcess], None]] = None,
    ) -> None:
        self._executable = Path(executable)
        self._gateway = gateway
        self._config = config or PoolConfig()
        self._lock = threading.RLock()
        self._processes: Dict[str, RuntimeProcess] = {}
        self._spawn_callbacks: list[Callable[[RuntimeProcess], None]] = []
        if on_spawn is not None:
            self._spawn_callbacks.append(on_spawn)
        self._port_cursor = self._config.base_port
        self._metrics: Deque[dict[str, Any]] = deque(maxlen=64)
        self._desired_runtimes = self._bound_capacity(
            self._config.desired_runtimes if self._config.desired_runtimes is not None else self._config.min_runtimes
        )

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            self._ensure_capacity_locked()

    def stop(self) -> None:
        with self._lock:
            procs = list(self._processes.values())
            self._processes.clear()
        for proc in procs:
            self._stop_process(proc, unregister=True)

    # ------------------------------------------------------------------
    def spawn(
        self,
        *,
        name: Optional[str] = None,
        extra_env: Optional[dict[str, str]] = None,
        port: Optional[int] = None,
    ) -> RuntimeProcess:
        with self._lock:
            runtime_proc = self._spawn_locked(name=name, extra_env=extra_env, port=port)
            self._desired_runtimes = max(self._desired_runtimes, len(self._processes))
        for callback in self._spawn_callbacks:
            callback(runtime_proc)
        return runtime_proc

    def remove(self, name: str) -> bool:
        with self._lock:
            proc = self._processes.pop(name, None)
            if proc is None:
                return False
            self._desired_runtimes = max(self._config.min_runtimes, min(self._desired_runtimes, len(self._processes)))
        self._stop_process(proc, unregister=True)
        return True

    # ------------------------------------------------------------------
    def set_desired_capacity(self, desired: int) -> None:
        with self._lock:
            self._desired_runtimes = self._bound_capacity(desired)
            self._ensure_capacity_locked()

    def scale_to(self, desired: int) -> None:
        self.set_desired_capacity(desired)

    @property
    def desired_capacity(self) -> int:
        with self._lock:
            return self._desired_runtimes

    def active_count(self) -> int:
        with self._lock:
            return sum(1 for proc in self._processes.values() if proc.is_alive())

    # ------------------------------------------------------------------
    def inspect(self) -> dict[str, Any]:
        with self._lock:
            procs = list(self._processes.values())
            metrics = list(self._metrics)
            active = sum(1 for proc in procs if proc.is_alive())
        return {
            "workers": [self._describe_process(proc) for proc in procs],
            "metrics": metrics,
            "desired": self._desired_runtimes,
            "active": active,
            "capacity": {
                "min": self._config.min_runtimes,
                "max": self._config.max_runtimes,
            },
        }

    def heartbeat(self) -> None:
        with self._lock:
            self._ensure_capacity_locked()

            to_restart: list[RuntimeProcess] = []
            for proc in list(self._processes.values()):
                if not proc.is_alive():
                    to_restart.append(proc)
            for proc in to_restart:
                self._restart_locked(proc)

            now = time.time()
            workers_snapshot: dict[str, dict[str, Any]] = {}
            alive_count = 0
            total_restarts = 0
            for proc in self._processes.values():
                health = self._collect_health(proc, now)
                proc.last_health = health
                workers_snapshot[proc.name] = health
                if health["alive"]:
                    alive_count += 1
                total_restarts += proc.restarts
                self._gateway.register(
                    RuntimeEndpoint(
                        name=proc.name,
                        protocol="http",
                        address=f"http://127.0.0.1:{proc.port}",
                        metadata={
                            "status": "ready" if health["alive"] else "stopped",
                            "pid": proc.process.pid,
                            "restarts": proc.restarts,
                            "cpu_percent": health.get("cpu_percent"),
                            "memory_rss": health.get("memory_rss"),
                        },
                    )
                )

            if workers_snapshot:
                summary = {
                    "timestamp": now,
                    "desired": self._desired_runtimes,
                    "total": len(self._processes),
                    "alive": alive_count,
                    "dead": len(self._processes) - alive_count,
                    "restarts": total_restarts,
                }
                self._metrics.appendleft({"summary": summary, "workers": workers_snapshot})

    # ------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            workers = [self._describe_process(proc) for proc in self._processes.values()]
            metrics = list(self._metrics)
            active = sum(1 for proc in self._processes.values() if proc.is_alive())
        return {
            "workers": workers,
            "metrics": metrics,
            "desired": self._desired_runtimes,
            "active": active,
            "capacity": {
                "min": self._config.min_runtimes,
                "max": self._config.max_runtimes,
            },
        }

    # ------------------------------------------------------------------
    def _ensure_capacity_locked(self) -> None:
        target = self._desired_runtimes
        current = len(self._processes)

        while current < target:
            self._spawn_locked()
            current += 1

        while current > target:
            self._shrink_locked()
            current -= 1

    def _spawn_locked(
        self,
        *,
        name: Optional[str] = None,
        extra_env: Optional[dict[str, str]] = None,
        port: Optional[int] = None,
    ) -> RuntimeProcess:
        if 0 < self._config.max_runtimes <= len(self._processes):
            raise RuntimeError("Maximum runtime capacity reached")

        worker_index = len(self._processes) + 1
        worker_name = name or f"runtime-{worker_index}"
        if worker_name in self._processes:
            raise RuntimeError(f"Worker {worker_name!r} already exists")

        assigned_port = port if port is not None else self._port_cursor
        if port is None:
            self._port_cursor += 1
        else:
            self._port_cursor = max(self._port_cursor, assigned_port + 1)

        env = dict(extra_env or {})
        env.setdefault("PYTHONPATH", str(Path(__file__).resolve().parents[1]))
        env["RUNTIME_PORT"] = str(assigned_port)
        env["RUNTIME_NAME"] = worker_name

        cmd = [sys.executable, str(self._executable), "--port", str(assigned_port)]
        process = subprocess.Popen(cmd, cwd=self._executable.parent, env=env)  # noqa: S603,S607
        runtime_proc = RuntimeProcess(
            name=worker_name,
            command=cmd,
            cwd=self._executable.parent,
            env=env,
            port=assigned_port,
            process=process,
            started_at=time.time(),
        )
        self._processes[worker_name] = runtime_proc
        self._register_endpoint_locked(runtime_proc)
        return runtime_proc

    def _shrink_locked(self) -> None:
        if not self._processes:
            return
        # Prefer removing the most recently started worker to minimise churn.
        name, proc = max(self._processes.items(), key=lambda item: item[1].started_at)
        self._processes.pop(name, None)
        self._stop_process(proc, unregister=True)

    def _restart_locked(self, proc: RuntimeProcess) -> None:
        name = proc.name
        self._processes.pop(name, None)
        self._stop_process(proc, unregister=True)
        time.sleep(max(0.0, float(self._config.restart_backoff)))
        new_proc = self._spawn_locked(name=name, extra_env=proc.env, port=proc.port)
        new_proc.restarts = proc.restarts + 1

    def _register_endpoint_locked(self, proc: RuntimeProcess) -> None:
        endpoint = RuntimeEndpoint(
            name=proc.name,
            protocol="http",
            address=f"http://127.0.0.1:{proc.port}",
            metadata={"status": "booting", "pid": proc.process.pid, "port": proc.port},
        )
        self._gateway.register(endpoint)

    def _stop_process(self, proc: RuntimeProcess, *, unregister: bool) -> None:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.process.wait(timeout=self._config.shutdown_timeout)
        if proc.is_alive():
            proc.kill()
        if unregister:
            self._gateway.unregister("http", proc.name)

    def _collect_health(self, proc: RuntimeProcess, now: float) -> dict[str, Any]:
        info = {
            "name": proc.name,
            "pid": proc.process.pid,
            "alive": proc.is_alive(),
            "uptime": max(0.0, now - proc.started_at),
            "restarts": proc.restarts,
            "port": proc.port,
            "last_heartbeat_at": now,
        }

        if info["alive"] and psutil is not None:
            try:
                ps_proc = psutil.Process(proc.process.pid)  # type: ignore[arg-type]
                with ps_proc.oneshot():
                    info["cpu_percent"] = ps_proc.cpu_percent(interval=0.0)
                    info["memory_rss"] = ps_proc.memory_info().rss
                    info["num_threads"] = ps_proc.num_threads()
            except Exception:  # pragma: no cover - psutil failures are non-fatal
                info.setdefault("cpu_percent", None)
                info.setdefault("memory_rss", None)
                info.setdefault("num_threads", None)
        else:
            info.setdefault("cpu_percent", None)
            info.setdefault("memory_rss", None)
            info.setdefault("num_threads", None)

        return info

    def _describe_process(self, proc: RuntimeProcess) -> dict[str, Any]:
        base = {
            "name": proc.name,
            "pid": proc.process.pid,
            "alive": proc.is_alive(),
            "uptime": max(0.0, time.time() - proc.started_at),
            "restarts": proc.restarts,
            "port": proc.port,
        }
        if proc.last_health:
            enriched = {k: v for k, v in proc.last_health.items() if k not in {"name"}}
            base.update(enriched)
        return base

    def _bound_capacity(self, desired: int) -> int:
        desired = max(0, int(desired))
        if desired < self._config.min_runtimes:
            desired = self._config.min_runtimes
        max_cap = self._config.max_runtimes
        if max_cap > 0:
            desired = min(desired, max_cap)
        return desired


__all__ = ["RuntimePool", "PoolConfig", "RuntimeProcess"]
