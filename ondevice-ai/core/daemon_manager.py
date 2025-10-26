"""Utilities for managing the automation daemon lifecycle from the CLI."""
from __future__ import annotations

import json
import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

import psutil  # type: ignore[import-untyped]

from core.config import get_config

_STATE_DIR_ENV = "MAHI_STATE_DIR"
_DEFAULT_STATE_SUBDIR = "mahi"
_PID_FILENAME = "daemon.pid"
_LOG_FILENAME = "daemon.log"
_SUPERVISOR_STATE_FILENAME = "supervisor_state.json"
_STARTUP_GRACE_SECONDS = 1.0


def _state_dir(override: Path | None = None) -> Path:
    if override is not None:
        path = override
    else:
        env = os.environ.get(_STATE_DIR_ENV)
        if env:
            path = Path(env).expanduser().resolve()
        else:
            path = Path.home() / f".{_DEFAULT_STATE_SUBDIR}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _pid_file_path(state_dir: Path | None = None) -> Path:
    return _state_dir(state_dir) / _PID_FILENAME


def _log_file_path(state_dir: Path | None = None) -> Path:
    return _state_dir(state_dir) / _LOG_FILENAME


def _supervisor_state_path(state_dir: Path | None = None) -> Path:
    return _state_dir(state_dir) / _SUPERVISOR_STATE_FILENAME


def _read_pid(state_dir: Path | None = None) -> Optional[int]:
    pid_file = _pid_file_path(state_dir)
    if not pid_file.exists():
        return None
    try:
        return int(pid_file.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _write_pid(pid: int, state_dir: Path | None = None) -> None:
    pid_file = _pid_file_path(state_dir)
    pid_file.write_text(str(pid), encoding="utf-8")


def _clear_pid(state_dir: Path | None = None) -> None:
    pid_file = _pid_file_path(state_dir)
    try:
        pid_file.unlink()
    except FileNotFoundError:
        return


def _clear_supervisor_state(state_dir: Path | None = None) -> None:
    state_file = _supervisor_state_path(state_dir)
    try:
        state_file.unlink()
    except FileNotFoundError:
        return


def _load_supervisor_state(state_dir: Path | None = None) -> dict[str, object]:
    state_file = _supervisor_state_path(state_dir)
    if not state_file.exists():
        return {}
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _coerce_int(value: object | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):  # bool is int subclass; respect explicit values
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return None
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _coerce_float(value: object | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


@dataclass
class DaemonStatus:
    running: bool
    pid: Optional[int]
    created_at: Optional[float] = None
    cmd: Optional[str] = None
    uptime_seconds: Optional[float] = None
    child_pid: Optional[int] = None
    restart_count: int = 0
    last_exit_code: Optional[int] = None
    last_start_time: Optional[float] = None
    last_exit_time: Optional[float] = None
    message: str | None = None
    health_status: Optional[str] = None
    health_url: Optional[str] = None


def _process_from_pid(pid: int) -> psutil.Process | None:
    try:
        process = psutil.Process(pid)
    except psutil.Error:
        return None
    if not process.is_running():
        return None
    try:
        process.status()
    except psutil.Error:
        return None
    return process


def daemon_status(state_dir: Path | None = None) -> DaemonStatus:
    pid = _read_pid(state_dir)
    state = _load_supervisor_state(state_dir)
    child_pid = _coerce_int(state.get("child_pid"))
    restart_count = _coerce_int(state.get("restart_count")) or 0
    last_exit_code = _coerce_int(state.get("last_exit_code"))
    last_start_time = _coerce_float(state.get("last_start_time"))
    last_exit_time = _coerce_float(state.get("last_exit_time"))
    health_status = None
    health_url = None

    health_info = state.get("health")
    if isinstance(health_info, dict):
        status_value = health_info.get("status")
        if isinstance(status_value, str):
            health_status = status_value

    endpoint_info = state.get("health_endpoint")
    if isinstance(endpoint_info, dict):
        host = endpoint_info.get("host")
        port_value = _coerce_int(endpoint_info.get("port"))
        path = endpoint_info.get("path")
        if isinstance(host, str) and port_value is not None:
            suffix = path if isinstance(path, str) else "/healthz"
            health_url = f"http://{host}:{port_value}{suffix}"

    if pid is None:
        message = "Daemon not running (missing PID file)."
        if last_exit_code is not None:
            message = f"Daemon stopped (last exit code {last_exit_code})."
        return DaemonStatus(
            running=False,
            pid=None,
            child_pid=child_pid,
            restart_count=restart_count,
            last_exit_code=last_exit_code,
            last_start_time=last_start_time,
            last_exit_time=last_exit_time,
            message=message,
            health_status=health_status,
            health_url=health_url,
        )
    process = _process_from_pid(pid)
    if process is None:
        _clear_pid(state_dir)
        return DaemonStatus(running=False, pid=None, message="Stale PID file found; daemon is not running.")
    created = process.create_time() if process else None
    cmdline = " ".join(process.cmdline()) if process else None
    uptime = time.time() - created if created else None
    message = "Daemon supervisor is running." if state else "Daemon is running."
    if health_status:
        message = f"{message} (health={health_status})"

    return DaemonStatus(
        running=True,
        pid=pid,
        created_at=created,
        cmd=cmdline,
        uptime_seconds=uptime,
        child_pid=child_pid,
        restart_count=restart_count,
        last_exit_code=last_exit_code,
        last_start_time=last_start_time,
        last_exit_time=last_exit_time,
        message=message,
        health_status=health_status,
        health_url=health_url,
    )


def _python_executable() -> str:
    return sys.executable or sys.argv[0]


def start_daemon(
    *,
    args: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    state_dir: Path | None = None,
    python_executable: Optional[str] = None,
    wait: float = _STARTUP_GRACE_SECONDS,
) -> DaemonStatus:
    status = daemon_status(state_dir)
    if status.running:
        raise RuntimeError("Automation daemon is already running.")

    daemon_script = Path(__file__).resolve().parents[1] / "automation_daemon.py"
    if not daemon_script.exists():
        raise FileNotFoundError(f"Unable to locate automation daemon script at {daemon_script}")

    supervisor_script = Path(__file__).resolve().parents[1] / "supervisor_main.py"
    if not supervisor_script.exists():
        raise FileNotFoundError(f"Unable to locate supervisor entrypoint at {supervisor_script}")

    config_data = get_config()
    supervisor_cfg_raw = config_data.get("supervisor") if isinstance(config_data, dict) else {}
    supervisor_enabled = True
    if isinstance(supervisor_cfg_raw, dict):
        supervisor_enabled = bool(supervisor_cfg_raw.get("enabled", True))
    else:
        supervisor_cfg_raw = {}

    state_path = _state_dir(state_dir)
    log_path = _log_file_path(state_dir)
    state_file = _supervisor_state_path(state_dir)

    python_exec = python_executable or _python_executable()
    child_cmd = [python_exec, str(daemon_script)]
    if args:
        child_cmd.extend(args)

    env_vars = dict(os.environ)
    if env:
        env_vars.update(env)

    if supervisor_enabled:
        supervisor_cmd = [
            python_exec,
            str(supervisor_script),
            "--log-file",
            str(log_path),
            "--state-file",
            str(state_file),
        ]
        supervisor_cmd.append("--")
        supervisor_cmd.extend(child_cmd)
        _clear_supervisor_state(state_dir)
        log_handle = log_path.open("a", encoding="utf-8")
        try:
            if platform.system() == "Windows":
                process = subprocess.Popen(  # type: ignore[arg-type]
                    supervisor_cmd,
                    stdout=log_handle,
                    stderr=log_handle,
                    cwd=str(supervisor_script.parent),
                    env=env_vars,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,  # type: ignore[attr-defined]
                )
            else:
                process = subprocess.Popen(  # type: ignore[arg-type]
                    supervisor_cmd,
                    stdout=log_handle,
                    stderr=log_handle,
                    cwd=str(supervisor_script.parent),
                    env=env_vars,
                    start_new_session=True,
                )
        finally:
            log_handle.close()
    else:
        _clear_supervisor_state(state_dir)
        log_handle = log_path.open("a", encoding="utf-8")
        try:
            if platform.system() == "Windows":
                process = subprocess.Popen(  # type: ignore[arg-type]
                    child_cmd,
                    stdout=log_handle,
                    stderr=log_handle,
                    cwd=str(daemon_script.parent),
                    env=env_vars,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,  # type: ignore[attr-defined]
                )
            else:
                process = subprocess.Popen(  # type: ignore[arg-type]
                    child_cmd,
                    stdout=log_handle,
                    stderr=log_handle,
                    cwd=str(daemon_script.parent),
                    env=env_vars,
                    start_new_session=True,
                )
        finally:
            log_handle.close()
    _write_pid(process.pid, state_dir)

    # Give the daemon a short window to fail fast before reporting success.
    time.sleep(max(0.0, wait))
    running = psutil.pid_exists(process.pid)
    if not running:
        _clear_pid(state_dir)
        _clear_supervisor_state(state_dir)
        raise RuntimeError("Failed to launch automation daemon; see log for details.")

    return daemon_status(state_dir)


def stop_daemon(*, state_dir: Path | None = None, timeout: float = 10.0) -> DaemonStatus:
    pid = _read_pid(state_dir)
    if pid is None:
        return DaemonStatus(running=False, pid=None, message="Daemon is not running.")

    process = _process_from_pid(pid)
    if process is None:
        _clear_pid(state_dir)
        _clear_supervisor_state(state_dir)
        return DaemonStatus(running=False, pid=None, message="Stale PID cleared.")

    try:
        if platform.system() == "Windows":
            process.terminate()
        else:
            process.send_signal(signal.SIGTERM)
        try:
            process.wait(timeout=timeout)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=timeout)
    finally:
        _clear_pid(state_dir)
        _clear_supervisor_state(state_dir)

    return DaemonStatus(running=False, pid=None, message="Daemon stopped.")


def restart_daemon(
    *,
    args: Sequence[str] | None = None,
    env: Mapping[str, str] | None = None,
    state_dir: Path | None = None,
    python_executable: Optional[str] = None,
    wait: float = _STARTUP_GRACE_SECONDS,
) -> DaemonStatus:
    stop_daemon(state_dir=state_dir)
    return start_daemon(args=args, env=env, state_dir=state_dir, python_executable=python_executable, wait=wait)


def state_directory(state_dir: Path | None = None) -> Path:
    """Return the state directory used for pid/log storage."""
    return _state_dir(state_dir)


def log_file_path(state_dir: Path | None = None) -> Path:
    """Return the daemon log file path."""
    return _log_file_path(state_dir)


__all__ = [
    "DaemonStatus",
    "daemon_status",
    "start_daemon",
    "stop_daemon",
    "restart_daemon",
    "state_directory",
    "log_file_path",
]
