"""Process supervision utilities for the automation daemon."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Deque, Iterable, Mapping, Sequence, TextIO


@dataclass
class SupervisorConfig:
    max_restarts: int = 5
    window_seconds: float = 60.0
    backoff_seconds: float = 2.0
    max_backoff_seconds: float = 30.0
    graceful_shutdown_seconds: float = 10.0
    health_enabled: bool = True
    health_host: str = "127.0.0.1"
    health_port: int = 0
    health_path: str = "/healthz"

    @classmethod
    def from_mapping(cls, data: Mapping[str, object] | None) -> "SupervisorConfig":
        if not data:
            return cls()
        kwargs: dict[str, object] = {}
        for field in (
            "max_restarts",
            "window_seconds",
            "backoff_seconds",
            "max_backoff_seconds",
            "graceful_shutdown_seconds",
            "health_enabled",
            "health_host",
            "health_port",
            "health_path",
        ):
            value = data.get(field)
            if value is not None:
                kwargs[field] = value
        return cls(**kwargs)  # type: ignore[arg-type]


@dataclass
class SupervisorHooks:
    on_child_start: Callable[[int, int], None] | None = None
    on_child_exit: Callable[[int | None, int], None] | None = None
    on_restart: Callable[[int], None] | None = None


class Supervisor:
    """Supervise a subprocess with restart/backoff logic."""

    def __init__(
        self,
        command: Sequence[str],
        *,
        log_path: Path,
        state_file: Path,
        config: SupervisorConfig | None = None,
        env: Mapping[str, str] | Iterable[tuple[str, str]] | None = None,
        hooks: SupervisorHooks | None = None,
        register_signals: bool = True,
    ) -> None:
        if not command:
            raise ValueError("Supervisor requires a command to execute")
        self._command = list(command)
        self._log_path = log_path
        self._state_file = state_file
        self._config = config or SupervisorConfig()
        if env is None:
            self._env_pairs: list[tuple[str, str]] = []
        elif isinstance(env, Mapping):
            self._env_pairs = [(str(k), str(v)) for k, v in env.items()]
        else:
            self._env_pairs = [(str(k), str(v)) for k, v in env]

        self._hooks = hooks or SupervisorHooks()
        self._register_signals = register_signals

        self._stop_event = threading.Event()
        self._child: subprocess.Popen[bytes] | None = None
        self._restart_history: Deque[float] = deque()
        self._restart_count = 0
        self._last_exit_code: int | None = None
        self._last_start_time: float | None = None
        self._last_exit_time: float | None = None
        self._log_handle: TextIO | None = None

        self._health_lock = threading.Lock()
        self._health_payload: dict[str, object] = {
            "status": "initializing",
            "running": False,
            "child_pid": None,
            "restart_count": 0,
            "last_exit_code": None,
            "timestamp": time.time(),
        }
        self._health_server: ThreadingHTTPServer | None = None
        self._health_thread: threading.Thread | None = None
        self._health_endpoint: tuple[str, int] | None = None
        self._health_ready = threading.Event()

    # --- public API -----------------------------------------------------

    def run(self) -> int:
        """Run the supervisor loop until the child exits or we give up."""
        self._prepare()
        exit_code = 0
        try:
            while not self._stop_event.is_set():
                exit_code = self._spawn_and_monitor_child()
                if self._stop_event.is_set():
                    break
                if exit_code == 0:
                    self._log("Child exited cleanly; stopping supervision.")
                    break
                if not self._should_restart():
                    self._log("Restart budget exhausted; stopping supervision.")
                    break
                delay = self._next_backoff_delay()
                if delay > 0:
                    self._log(f"Restarting child after {delay:.1f}s backoff.")
                    if self._stop_event.wait(delay):
                        break
                else:
                    self._log("Restarting child immediately.")
        finally:
            self._teardown()
        return exit_code

    def stop(self) -> None:
        """Request the supervisor to terminate and stop restarting."""
        self._log("Stop requested.")
        self._stop_event.set()
        child_pid: int | None = None
        if self._child and self._child.poll() is None:
            child_pid = self._child.pid
        self._set_health_status(status="stopping", running=child_pid is not None, child_pid=child_pid)
        self._terminate_child()

    # --- internal helpers -----------------------------------------------

    def _prepare(self) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_file.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self._log_path.open("a", encoding="utf-8")
        self._log("Supervisor starting.")
        self._set_health_status(status="initializing", running=False, child_pid=None)
        self._start_health_server()
        if self._register_signals:
            signal.signal(signal.SIGTERM, self._handle_signal)
            signal.signal(signal.SIGINT, self._handle_signal)

    def _teardown(self) -> None:
        self._terminate_child()
        self._set_health_status(status="stopped", running=False, child_pid=None)
        if self._log_handle is not None:
            self._log("Supervisor stopped.")
            self._log_handle.close()
            self._log_handle = None
        self._stop_health_server()
        if self._register_signals:
            try:
                signal.signal(signal.SIGTERM, signal.SIG_DFL)
                signal.signal(signal.SIGINT, signal.SIG_DFL)
            except Exception:
                pass

    def _spawn_and_monitor_child(self) -> int:
        self._cleanup_restart_history()
        self._last_start_time = time.time()
        env = dict(os.environ)
        env.update(self._env_pairs)
        self._log(f"Launching child: {' '.join(self._command)}")
        if os.name == "nt":
            self._child = subprocess.Popen(
                self._command,
                stdout=self._log_handle,
                stderr=self._log_handle,
                env=env,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # type: ignore[attr-defined]
            )
        else:
            self._child = subprocess.Popen(
                self._command,
                stdout=self._log_handle,
                stderr=self._log_handle,
                env=env,
                start_new_session=True,
            )
        self._set_health_status(status="ready", running=True, child_pid=self._child.pid, exit_code=None)
        if self._hooks.on_child_start:
            self._hooks.on_child_start(self._child.pid, self._restart_count)
        try:
            exit_code = self._child.wait()
        except Exception as exc:  # pragma: no cover - defensive
            self._log(f"Error waiting for child: {exc}")
            exit_code = 1
        self._last_exit_code = exit_code
        self._last_exit_time = time.time()
        self._log(f"Child exited with code {exit_code}.")
        status = "stopped" if exit_code == 0 else "failed"
        self._set_health_status(status=status, running=False, child_pid=None, exit_code=exit_code)
        if self._hooks.on_child_exit:
            self._hooks.on_child_exit(exit_code, self._restart_count)
        if exit_code != 0 and not self._stop_event.is_set():
            self._register_restart()
        return exit_code

    def _terminate_child(self) -> None:
        child = self._child
        if not child or child.poll() is not None:
            return
        grace = max(0.0, float(self._config.graceful_shutdown_seconds))
        if os.name == "nt":
            self._log("Sending CTRL_BREAK_EVENT to child process group.")
            try:
                child.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            except Exception:
                pass
        else:
            self._log("Sending SIGTERM to child process group.")
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                return
        try:
            child.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            self._log("Child did not exit in time; killing.")
            try:
                if os.name == "nt":
                    child.kill()
                else:
                    os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            else:
                child.wait()

    def _register_restart(self) -> None:
        now = time.time()
        self._restart_history.append(now)
        self._restart_count += 1
        self._cleanup_restart_history()
        self._set_health_status(status="restarting", running=False, child_pid=None)
        if self._hooks.on_restart:
            self._hooks.on_restart(self._restart_count)

    def _cleanup_restart_history(self) -> None:
        window = max(0.0, float(self._config.window_seconds))
        if window <= 0:
            self._restart_history.clear()
            return
        threshold = time.time() - window
        while self._restart_history and self._restart_history[0] < threshold:
            self._restart_history.popleft()

    def _should_restart(self) -> bool:
        max_restarts = max(0, int(self._config.max_restarts))
        if max_restarts == 0:
            return False
        return len(self._restart_history) < max_restarts

    def _next_backoff_delay(self) -> float:
        base = max(0.0, float(self._config.backoff_seconds))
        if base == 0:
            return 0.0
        attempt = max(0, len(self._restart_history) - 1)
        delay = base * (2 ** attempt)
        return min(float(self._config.max_backoff_seconds), delay)

    def _handle_signal(self, signum: int, frame) -> None:  # pragma: no cover - signal handler
        self._log(f"Received signal {signum}; shutting down child.")
        self.stop()

    def _log(self, message: str) -> None:
        if self._log_handle is None:
            return
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        self._log_handle.write(f"[supervisor {timestamp}] {message}\n")
        self._log_handle.flush()

    def _start_health_server(self) -> None:
        if not self._config.health_enabled:
            self._health_ready.set()
            return

        host = (self._config.health_host or "127.0.0.1").strip() or "127.0.0.1"
        try:
            port = int(self._config.health_port)
        except (TypeError, ValueError):
            port = 0
        path = (self._config.health_path or "/healthz")
        supervisor = self

        class _HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):  # type: ignore[override]
                normalized = self.path.split("?")[0]
                if normalized not in {path, "/health", "/healthz"}:
                    self.send_response(404)
                    self.end_headers()
                    return
                payload = supervisor._health_snapshot()
                status_code = 200 if payload.get("status") == "ready" else 503
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args) -> None:  # pragma: no cover - suppress noisy logs
                return

        class _HealthServer(ThreadingHTTPServer):
            daemon_threads = True
            allow_reuse_address = True

        try:
            server = _HealthServer((host, port), _HealthHandler)
        except OSError as exc:  # pragma: no cover - port in use
            self._log(f"Failed to start health server: {exc}")
            self._health_ready.set()
            return

        actual_port = server.server_address[1]
        self._health_server = server
        self._health_endpoint = (host, actual_port)
        self._health_thread = threading.Thread(target=server.serve_forever, name="supervisor-health", daemon=True)
        self._health_thread.start()
        self._health_ready.set()
        self._write_state(running=bool(self._health_payload.get("running")), child_pid=None)

    def _stop_health_server(self) -> None:
        server = self._health_server
        if server is None:
            self._health_ready.set()
            return
        server.shutdown()
        server.server_close()
        if self._health_thread is not None:
            self._health_thread.join(timeout=1.0)
        self._health_server = None
        self._health_thread = None
        self._health_endpoint = None
        self._health_ready.set()

    def _set_health_status(
        self,
        *,
        status: str,
        running: bool,
        child_pid: int | None,
        exit_code: int | None = None,
    ) -> None:
        with self._health_lock:
            payload = dict(self._health_payload)
            payload.update({
                "status": status,
                "running": running,
                "child_pid": child_pid,
                "restart_count": self._restart_count,
                "last_exit_code": exit_code if exit_code is not None else self._last_exit_code,
                "timestamp": time.time(),
            })
            self._health_payload = payload
        self._write_state(running=running, child_pid=child_pid)

    def _health_snapshot(self) -> dict[str, object]:
        with self._health_lock:
            return dict(self._health_payload)

    @property
    def health_endpoint(self) -> tuple[str, int] | None:
        return self._health_endpoint

    def wait_for_health(self, timeout: float | None = None) -> bool:
        return self._health_ready.wait(timeout)

    def _write_state(self, *, running: bool, child_pid: int | None = None) -> None:
        health_snapshot = self._health_snapshot()
        state = {
            "timestamp": time.time(),
            "running": running,
            "child_pid": child_pid if running else None,
            "restart_count": self._restart_count,
            "last_exit_code": self._last_exit_code,
            "last_start_time": self._last_start_time,
            "last_exit_time": self._last_exit_time,
            "health": health_snapshot,
        }
        if self._health_endpoint is not None:
            state["health_endpoint"] = {
                "host": self._health_endpoint[0],
                "port": self._health_endpoint[1],
                "path": self._config.health_path,
            }
        try:
            self._state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
        except OSError:
            self._log("Failed to write supervisor state file.")


__all__ = ["Supervisor", "SupervisorConfig", "SupervisorHooks"]
