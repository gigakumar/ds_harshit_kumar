"""Sandboxed execution harness for automation actions."""
from __future__ import annotations

import asyncio
import builtins
import contextlib
import importlib
import io
import multiprocessing
import os
import resource
import socket
import sys
import time
import traceback
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(slots=True)
class SandboxPermissions:
    """High-level permission switches sourced from configuration."""

    file_access: bool = False
    network_access: bool = False
    calendar_access: bool = False
    mail_access: bool = False
    browser_access: bool = False

    def allows(self, permission: str) -> bool:
        try:
            return bool(getattr(self, permission))
        except AttributeError as exc:  # pragma: no cover - guard for unknown flags
            raise KeyError(f"Unknown permission '{permission}'") from exc

    def as_dict(self) -> dict[str, bool]:
        return asdict(self)


@dataclass(slots=True)
class SandboxConfig:
    """Tunable limits and environment options for the sandbox."""

    cpu_time_seconds: int = 5
    wall_time_seconds: float = 10.0
    memory_bytes: int = 512 * 1024 * 1024
    working_dir: Path = Path("./sandbox")
    env: Mapping[str, str] | None = None
    allow_subprocesses: bool = False
    allow_network: bool = False
    max_open_files: int | None = 256
    max_processes: int | None = 64
    max_output_bytes: int | None = 64 * 1024 * 1024
    idle_priority: bool = True
    nice_increment: int = 10
    collect_usage: bool = True

    def __post_init__(self) -> None:
        self.working_dir = Path(self.working_dir).resolve()

    @classmethod
    def mac_defaults(
        cls,
        *,
        working_dir: Path | str | None = None,
        env: Mapping[str, str] | None = None,
    ) -> "SandboxConfig":
        base_dir = Path(working_dir) if working_dir is not None else Path("./sandbox")
        return cls(
            cpu_time_seconds=10,
            wall_time_seconds=15.0,
            memory_bytes=1_024 * 1024 * 1024,
            working_dir=base_dir,
            env=env,
            allow_subprocesses=False,
            allow_network=False,
            max_open_files=512,
            max_processes=128,
            max_output_bytes=256 * 1024 * 1024,
            idle_priority=True,
            nice_increment=10,
            collect_usage=True,
        )


@dataclass(slots=True)
class SandboxAction:
    """Descriptor for an executable unit within the sandbox."""

    target: str
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)
    required_permissions: tuple[str, ...] = ()


@dataclass(slots=True)
class SandboxResult:
    success: bool
    value: Any | None
    stdout: str
    stderr: str
    duration: float
    timed_out: bool
    error: str | None = None
    limits: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None


class SandboxHarness:
    """Execute automation actions inside a locked-down worker process."""

    def __init__(
        self,
        *,
        config: SandboxConfig | None = None,
        permissions: SandboxPermissions | None = None,
    ) -> None:
        self.config = config or SandboxConfig()
        self.permissions = permissions or SandboxPermissions()
        self.config.working_dir.mkdir(parents=True, exist_ok=True)
        self._ctx = multiprocessing.get_context("spawn")

    def execute(self, action: SandboxAction) -> SandboxResult:
        denied = [scope for scope in action.required_permissions if not self.permissions.allows(scope)]
        if denied:
            denied_scopes = ", ".join(sorted(denied))
            raise PermissionError(f"Action '{action.target}' requires disabled permissions: {denied_scopes}")

        queue: multiprocessing.Queue[Any] = self._ctx.Queue()  # type: ignore[assignment]
        process = self._ctx.Process(
            target=_worker_entry,
            args=(
                queue,
                {
                    "target": action.target,
                    "args": action.args,
                    "kwargs": action.kwargs,
                    "permissions": action.required_permissions,
                },
                {
                    "cpu_time_seconds": self.config.cpu_time_seconds,
                    "wall_time_seconds": self.config.wall_time_seconds,
                    "memory_bytes": self.config.memory_bytes,
                    "working_dir": str(self.config.working_dir),
                    "env": dict(self.config.env or {}),
                    "allow_subprocesses": self.config.allow_subprocesses,
                    "allow_network": self.config.allow_network,
                    "allow_files": self.permissions.file_access,
                    "max_open_files": self.config.max_open_files,
                    "max_processes": self.config.max_processes,
                    "max_output_bytes": self.config.max_output_bytes,
                    "idle_priority": self.config.idle_priority,
                    "nice_increment": self.config.nice_increment,
                    "collect_usage": self.config.collect_usage,
                },
            ),
            daemon=True,
        )

        start_time = time.time()
        process.start()
        process.join(timeout=self.config.wall_time_seconds)
        timed_out = False
        payload: dict[str, Any] | None = None

        if process.is_alive():
            timed_out = True
            process.kill()
            process.join(timeout=1.0)
        else:
            try:
                payload = queue.get_nowait()
            except Exception:
                payload = None

        duration = time.time() - start_time

        if timed_out:
            return SandboxResult(
                success=False,
                value=None,
                stdout="",
                stderr="",
                duration=duration,
                timed_out=True,
                error="Timed out waiting for sandbox action",
            )

        if not payload:
            return SandboxResult(
                success=False,
                value=None,
                stdout="",
                stderr="",
                duration=duration,
                timed_out=False,
                error="Sandbox process exited without result",
            )

        status = payload.get("status")
        stdout = payload.get("stdout", "")
        stderr = payload.get("stderr", "")
        limits = payload.get("limits") if isinstance(payload.get("limits"), dict) else None
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else None
        if status == "ok":
            return SandboxResult(
                success=True,
                value=payload.get("result"),
                stdout=stdout,
                stderr=stderr,
                duration=payload.get("duration", duration),
                timed_out=False,
                error=None,
                limits=limits,
                usage=usage,
            )

        return SandboxResult(
            success=False,
            value=None,
            stdout=stdout,
            stderr=stderr,
            duration=duration,
            timed_out=False,
            error=payload.get("error", "Unknown sandbox failure"),
            limits=limits,
            usage=usage,
        )

    def update_permissions(self, permissions: SandboxPermissions) -> None:
        self.permissions = permissions
        self.config.allow_network = permissions.network_access


def _worker_entry(
    queue: multiprocessing.Queue[Any],
    action_payload: Mapping[str, Any],
    config_payload: Mapping[str, Any],
) -> None:
    start = time.time()
    stdout_buffer = io.StringIO()
    stderr_buffer = io.StringIO()
    try:
        limits_snapshot = _apply_limits(config_payload)
    except Exception:
        limits_snapshot = {}
    collect_usage = bool(config_payload.get("collect_usage", False))
    try:
        with redirect_stdout(stdout_buffer), redirect_stderr(stderr_buffer):
            result = _invoke_target(
                str(action_payload.get("target")),
                tuple(action_payload.get("args", ())),
                dict(action_payload.get("kwargs", {})),
            )
        usage_snapshot = _collect_usage() if collect_usage else None
        queue.put(
            {
                "status": "ok",
                "result": result,
                "stdout": stdout_buffer.getvalue(),
                "stderr": stderr_buffer.getvalue(),
                "duration": time.time() - start,
                "limits": limits_snapshot,
                "usage": usage_snapshot,
            }
        )
    except Exception:
        usage_snapshot = _collect_usage() if collect_usage else None
        queue.put(
            {
                "status": "error",
                "error": traceback.format_exc(),
                "stdout": stdout_buffer.getvalue(),
                "stderr": stderr_buffer.getvalue(),
                "limits": limits_snapshot,
                "usage": usage_snapshot,
            }
        )
    finally:
        stdout_buffer.close()
        stderr_buffer.close()


def _apply_limits(config_payload: Mapping[str, Any]) -> dict[str, Any]:
    working_dir = Path(str(config_payload.get("working_dir", "."))).resolve()
    working_dir.mkdir(parents=True, exist_ok=True)
    os.chdir(working_dir)

    env_overrides = dict(config_payload.get("env", {}))
    os.environ.update(env_overrides)

    cpu_time = int(config_payload.get("cpu_time_seconds", 0))
    if cpu_time > 0:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_time, cpu_time))

    memory_bytes = int(config_payload.get("memory_bytes", 0))
    if memory_bytes > 0:
        with contextlib.suppress(ValueError, OSError):
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

    max_output = config_payload.get("max_output_bytes")
    if max_output:
        limit = max(0, int(max_output))
        if limit > 0 and hasattr(resource, "RLIMIT_FSIZE"):
            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))

    max_open_files = config_payload.get("max_open_files")
    if max_open_files:
        limit = max(0, int(max_open_files))
        if limit > 0 and hasattr(resource, "RLIMIT_NOFILE"):
            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(resource.RLIMIT_NOFILE, (limit, limit))

    max_processes = config_payload.get("max_processes")
    if max_processes and hasattr(resource, "RLIMIT_NPROC"):
        limit = max(0, int(max_processes))
        if limit > 0:
            with contextlib.suppress(ValueError, OSError):
                resource.setrlimit(resource.RLIMIT_NPROC, (limit, limit))

    allow_network = bool(config_payload.get("allow_network", False))
    if not allow_network:
        _disable_network()

    allow_files = bool(config_payload.get("allow_files", False))
    if not allow_files:
        _restrict_file_access(working_dir)

    allow_subprocesses = bool(config_payload.get("allow_subprocesses", False))
    if not allow_subprocesses:
        _disable_subprocess_creation()

    idle_priority = bool(config_payload.get("idle_priority", False))
    nice_increment = int(config_payload.get("nice_increment", 0))
    if idle_priority or nice_increment:
        _lower_process_priority(max(nice_increment, 1))

    return _snapshot_limits()


def _collect_usage() -> dict[str, Any]:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
    except Exception:
        return {}
    return {
        "user_time": usage.ru_utime,
        "system_time": usage.ru_stime,
        "max_rss": usage.ru_maxrss,
        "in_block_ops": usage.ru_inblock,
        "out_block_ops": usage.ru_oublock,
        "context_switches_voluntary": getattr(usage, "ru_nvcsw", 0),
        "context_switches_involuntary": getattr(usage, "ru_nivcsw", 0),
    }


def _snapshot_limits() -> dict[str, Any]:
    snapshot: dict[str, Any] = {}

    def _limit_tuple(resource_name: str, label: str) -> None:
        res_value = getattr(resource, resource_name, None)
        if res_value is None:
            return
        with contextlib.suppress(ValueError, OSError):
            soft, hard = resource.getrlimit(res_value)
            snapshot[label] = {"soft": soft, "hard": hard}

    _limit_tuple("RLIMIT_CPU", "cpu_time")
    _limit_tuple("RLIMIT_AS", "memory")
    _limit_tuple("RLIMIT_FSIZE", "output_size")
    _limit_tuple("RLIMIT_NOFILE", "open_files")
    _limit_tuple("RLIMIT_NPROC", "processes")

    try:
        priority = os.getpriority(os.PRIO_PROCESS, 0)
    except Exception:
        priority = None
    snapshot["priority"] = priority

    return snapshot


def _lower_process_priority(increment: int) -> None:
    if increment <= 0:
        return
    try:
        os.setpriority(os.PRIO_PROCESS, 0, min(20, os.getpriority(os.PRIO_PROCESS, 0) + increment))
    except Exception:
        with contextlib.suppress(Exception):
            os.nice(increment)


def _invoke_target(target: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    if ":" not in target:
        raise ValueError("Sandbox target must be in 'module:function' format")
    module_name, func_name = target.split(":", 1)
    module = importlib.import_module(module_name)
    fn = getattr(module, func_name)
    result = fn(*args, **kwargs)
    if asyncio.iscoroutine(result):
        return asyncio.run(result)
    return result


def _disable_network() -> None:
    def _raise_network_error(*_args: Any, **_kwargs: Any) -> Any:
        raise PermissionError("Network access is disabled in sandbox")

    socket.socket = _raise_network_error  # type: ignore[assignment]
    socket.create_connection = _raise_network_error  # type: ignore[assignment]
    socket.create_server = _raise_network_error  # type: ignore[assignment]


def _restrict_file_access(working_dir: Path) -> None:
    allowed_root = working_dir.resolve()
    original_open = builtins.open

    def _guarded_open(file: Any, *args: Any, **kwargs: Any):
        if isinstance(file, int):  # file descriptor
            return original_open(file, *args, **kwargs)
        path = Path(file)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        if not _is_within(path, allowed_root):
            raise PermissionError("File system access is restricted inside sandbox")
        return original_open(path, *args, **kwargs)

    builtins.open = _guarded_open  # type: ignore[assignment]


def _disable_subprocess_creation() -> None:
    import subprocess

    def _blocked_popen(*_args: Any, **_kwargs: Any):
        raise PermissionError("Subprocess creation is disabled in sandbox")

    subprocess.Popen = _blocked_popen  # type: ignore[assignment]


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


__all__ = [
    "SandboxAction",
    "SandboxConfig",
    "SandboxHarness",
    "SandboxPermissions",
    "SandboxResult",
]
