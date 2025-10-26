#!/usr/bin/env python
"""Automation daemon that hosts the gRPC orchestrator service and MLX runtime."""
from __future__ import annotations

import argparse
import os
import signal
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

from core.auth import AuthManager
from core.config import get_config, save_config
from core.gateway_server import GatewayServer
from core.orchestrator import Orchestrator
from core.runtime_gateway import RuntimeEndpoint, RuntimeGateway
from core.runtime_pool import PoolConfig, RuntimePool
from core.sandbox import SandboxAction, SandboxConfig, SandboxHarness, SandboxPermissions, SandboxResult
from core.server import create_server
from core.telemetry import collect_system_metrics
from tools.mlx_runtime import app as mlx_app
from werkzeug.serving import make_server


@dataclass
class DaemonHandle:
    grpc_server: Any
    flask_server: "_FlaskServer"
    grpc_host: str
    grpc_port: int
    mlx_host: str
    mlx_port: int
    gateway_server: GatewayServer
    gateway: RuntimeGateway
    stop_event: threading.Event
    started_at: float
    runtime_pool: RuntimePool | None
    pool_config: PoolConfig | None
    pool_monitor_stop: threading.Event | None
    pool_monitor_thread: threading.Thread | None
    document_counter: Callable[[], int] | None
    metrics_provider: Callable[[], dict[str, Any]]
    sandbox: SandboxHarness
    auth_manager: AuthManager
    _stopped: bool = False

    def stop(self) -> None:
        if self._stopped:
            return
        try:
            if self.pool_monitor_stop is not None:
                self.pool_monitor_stop.set()
            if self.pool_monitor_thread is not None:
                self.pool_monitor_thread.join(timeout=2.0)
        finally:
            if self.runtime_pool is not None:
                try:
                    self.runtime_pool.stop()
                except Exception:
                    pass
        try:
            self.grpc_server.stop(grace=0)
        finally:
            try:
                self.flask_server.shutdown()
            finally:
                try:
                    self.gateway_server.stop()
                finally:
                    self._stopped = True
                    self.stop_event.set()

    def wait(self, timeout: Optional[float] = None) -> bool:
        return self.stop_event.wait(timeout=timeout)

    @property
    def runtime_url(self) -> str:
        return f"http://{self.mlx_host}:{self.mlx_port}"

    @property
    def grpc_address(self) -> str:
        return f"{self.grpc_host}:{self.grpc_port}"

    @property
    def is_running(self) -> bool:
        return not self._stopped

    def system_metrics(self) -> dict[str, Any]:
        metrics = self.metrics_provider()
        if self.runtime_pool is not None:
            metrics.setdefault("runtime_pool", self.runtime_pool.snapshot())
        if "sandbox" not in metrics:
            metrics["sandbox"] = {
                "working_dir": str(self.sandbox.config.working_dir),
                "permissions": self.sandbox.permissions.as_dict(),
            }
        metrics.setdefault("uptime_seconds", max(0.0, time.time() - self.started_at))
        return metrics

    @property
    def auth_token(self) -> Optional[str]:
        return self.gateway_server.bootstrap_token

    def pool_snapshot(self) -> Optional[dict[str, Any]]:
        if self.runtime_pool is None:
            return None
        return self.runtime_pool.snapshot()

    def set_runtime_capacity(self, desired: int) -> None:
        if self.runtime_pool is None:
            raise RuntimeError("Runtime pool is not enabled")
        self.runtime_pool.scale_to(desired)

    @property
    def runtime_capacity(self) -> Optional[int]:
        if self.runtime_pool is None:
            return None
        return self.runtime_pool.desired_capacity

    @property
    def active_runtimes(self) -> Optional[int]:
        if self.runtime_pool is None:
            return None
        return self.runtime_pool.active_count()

    def execute_sandbox_action(self, action: SandboxAction) -> SandboxResult:
        return self.sandbox.execute(action)


class _FlaskServer(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self._host = host
        self._requested_port = port
        selected_port = _select_port(host, port)
        self._server = _create_server(host, selected_port)
        self._ctx = mlx_app.app_context()

    def run(self) -> None:
        self._ctx.push()
        try:
            self._server.serve_forever()
        finally:
            self._ctx.pop()

    def shutdown(self) -> None:
        self._server.shutdown()

    @property
    def port(self) -> int:
        return int(getattr(self._server, "server_port", self._requested_port))


def _create_server(host: str, port: int):
    try:
        return make_server(host, port, mlx_app)
    except OSError as exc:
        if port != 0:
            print(
                f"[daemon] Port {port} unavailable ({exc}). Retrying with an ephemeral port.",
                file=sys.stderr,
            )
            return make_server(host, 0, mlx_app)
        raise

def _select_port(host: str, requested: int) -> int:
    if requested == 0:
        return 0
    if _port_available(host, requested):
        return requested
    print(f"[daemon] Port {requested} unavailable. Falling back to an ephemeral port.", file=sys.stderr)
    return 0


def _port_available(host: str, port: int) -> bool:
    try:
        addrinfos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror:
        addrinfos = [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (host, port))]

    for family, socktype, proto, _, sockaddr in addrinfos:
        try:
            with socket.socket(family, socktype, proto) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(sockaddr)
        except OSError:
            continue
        else:
            return True
    return False


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the automation daemon.")
    parser.add_argument("--grpc-host", default="[::]", help="Host/interface for gRPC server")
    parser.add_argument("--grpc-port", type=int, default=50051, help="Port for gRPC server")
    parser.add_argument("--mlx-host", default="127.0.0.1", help="Host/interface for MLX HTTP runtime")
    parser.add_argument("--mlx-port", type=int, default=9000, help="Port for MLX HTTP runtime")
    parser.add_argument("--models-dir", help="Override ML models directory", default=None)
    return parser.parse_args(argv)


def start_daemon(
    *,
    grpc_host: str = "[::]",
    grpc_port: int = 50051,
    mlx_host: str = "127.0.0.1",
    mlx_port: int = 9000,
    models_dir: Optional[str] = None,
    stop_event: Optional[threading.Event] = None,
) -> DaemonHandle:
    if stop_event is None:
        stop_event = threading.Event()

    if models_dir:
        os.environ["ML_MODELS_DIR"] = os.path.abspath(models_dir)

    started_at = time.time()
    config = get_config()
    auth_manager = AuthManager.from_config(config)
    auth_cfg = config.get("auth", {}) if isinstance(config, dict) else {}
    bootstrap_configured = False
    if isinstance(auth_cfg, dict):
        bootstrap_configured = bool(str(auth_cfg.get("bootstrap_token", "")).strip())
    bootstrap_metadata = auth_manager.ensure_bootstrap_token()
    minted_bootstrap = (not bootstrap_configured) and (time.time() - bootstrap_metadata.issued_at < 2.0)
    gateway = RuntimeGateway()
    orchestrator = Orchestrator()

    pool_settings = config.get("runtime_pool", {}) if isinstance(config, dict) else {}
    pool_enabled = bool(pool_settings.get("enabled", False))
    runtime_pool: RuntimePool | None = None
    runtime_pool_config: PoolConfig | None = None
    pool_monitor_stop: threading.Event | None = None
    pool_monitor_thread: threading.Thread | None = None
    sandbox: SandboxHarness | None = None

    flask_server = _FlaskServer(host=mlx_host, port=mlx_port)
    actual_mlx_port = flask_server.port
    _sync_runtime_url(mlx_host, actual_mlx_port)

    grpc_server = create_server(host=grpc_host, port=grpc_port, orchestrator=orchestrator)
    bound_grpc_port = getattr(grpc_server, "_bound_port", grpc_port)

    gateway.bulk_register(
        (
            RuntimeEndpoint(
                name="grpc",
                protocol="grpc",
                address=f"{grpc_host}:{bound_grpc_port}",
                metadata={"status": "ready"},
            ),
            RuntimeEndpoint(
                name="mlx",
                protocol="http",
                address=f"http://{mlx_host}:{actual_mlx_port}",
                metadata={"status": "ready"},
            ),
        )
    )

    def _document_counter() -> int:
        try:
            return int(orchestrator.store.count_docs())
        except Exception:
            return 0

    def _metrics_provider() -> dict[str, Any]:
        metrics = collect_system_metrics(started_at=started_at, document_counter=_document_counter)
        if runtime_pool is not None:
            metrics["runtime_pool"] = runtime_pool.snapshot()
        if sandbox is not None:
            metrics["sandbox"] = {
                "working_dir": str(sandbox.config.working_dir),
                "permissions": sandbox.permissions.as_dict(),
                "limits": {
                    "cpu_time_seconds": sandbox.config.cpu_time_seconds,
                    "wall_time_seconds": sandbox.config.wall_time_seconds,
                    "memory_bytes": sandbox.config.memory_bytes,
                    "max_open_files": sandbox.config.max_open_files,
                    "max_processes": sandbox.config.max_processes,
                    "max_output_bytes": sandbox.config.max_output_bytes,
                    "idle_priority": sandbox.config.idle_priority,
                    "nice_increment": sandbox.config.nice_increment,
                },
            }
        elif "sandbox" not in metrics:
            default_config = SandboxConfig.mac_defaults() if sys.platform == "darwin" else SandboxConfig()
            default_permissions = SandboxPermissions()
            metrics["sandbox"] = {
                "working_dir": str(default_config.working_dir),
                "permissions": default_permissions.as_dict(),
                "limits": {
                    "cpu_time_seconds": default_config.cpu_time_seconds,
                    "wall_time_seconds": default_config.wall_time_seconds,
                    "memory_bytes": default_config.memory_bytes,
                    "max_open_files": default_config.max_open_files,
                    "max_processes": default_config.max_processes,
                    "max_output_bytes": default_config.max_output_bytes,
                    "idle_priority": default_config.idle_priority,
                    "nice_increment": default_config.nice_increment,
                },
            }
        return metrics

    gateway_server = GatewayServer(
        orchestrator=orchestrator,
        gateway=gateway,
        auth_manager=auth_manager,
        metrics_provider=_metrics_provider,
    )

    permissions_cfg = config.get("permissions", {}) if isinstance(config, dict) else {}
    sandbox_permissions = SandboxPermissions(
        file_access=bool(permissions_cfg.get("file_access", False)),
        network_access=bool(permissions_cfg.get("network_access", False)),
        calendar_access=bool(permissions_cfg.get("calendar_access", False)),
        mail_access=bool(permissions_cfg.get("mail_access", False)),
    )
    sandbox_settings = config.get("sandbox", {}) if isinstance(config, dict) else {}
    if not isinstance(sandbox_settings, dict):
        sandbox_settings = {}

    sandbox_workdir_override = sandbox_settings.get("working_dir")
    sandbox_workdir = sandbox_workdir_override or (config.get("paths", {}).get("sandbox_dir") if isinstance(config, dict) else None)
    sandbox_workdir_path = Path(sandbox_workdir).expanduser().resolve() if sandbox_workdir else Path.cwd() / "sandbox"

    def _sandbox_int(key: str, default: int) -> int:
        value = sandbox_settings.get(key)
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 0 else default

    def _sandbox_float(key: str, default: float) -> float:
        value = sandbox_settings.get(key)
        if value is None:
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _sandbox_bool(key: str, default: bool) -> bool:
        value = sandbox_settings.get(key)
        if value is None:
            return default
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in {"1", "true", "yes", "on"}:
                return True
            if lowered in {"0", "false", "no", "off"}:
                return False
        return bool(value)

    def _sandbox_limit(key: str, default: int | None) -> int | None:
        value = sandbox_settings.get(key)
        if value is None:
            return default
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        if parsed <= 0:
            return None
        return parsed

    env_overrides = sandbox_settings.get("env")
    env_mapping = env_overrides if isinstance(env_overrides, dict) else None

    mac_defaults = SandboxConfig.mac_defaults(working_dir=sandbox_workdir_path, env=env_mapping) if sys.platform == "darwin" else SandboxConfig(
        working_dir=sandbox_workdir_path,
        env=env_mapping,
        allow_subprocesses=False,
        allow_network=False,
    )

    allow_network_override = sandbox_settings.get("allow_network")
    allow_network = sandbox_permissions.network_access if allow_network_override is None else _sandbox_bool("allow_network", bool(allow_network_override))

    sandbox_config = SandboxConfig(
        cpu_time_seconds=_sandbox_int("cpu_time_seconds", mac_defaults.cpu_time_seconds),
        wall_time_seconds=_sandbox_float("wall_time_seconds", mac_defaults.wall_time_seconds),
        memory_bytes=_sandbox_int("memory_bytes", mac_defaults.memory_bytes),
        working_dir=mac_defaults.working_dir,
        env=mac_defaults.env,
        allow_subprocesses=_sandbox_bool("allow_subprocesses", mac_defaults.allow_subprocesses),
        allow_network=allow_network,
        max_open_files=_sandbox_limit("max_open_files", mac_defaults.max_open_files),
        max_processes=_sandbox_limit("max_processes", mac_defaults.max_processes),
        max_output_bytes=_sandbox_limit("max_output_bytes", mac_defaults.max_output_bytes),
        idle_priority=_sandbox_bool("idle_priority", mac_defaults.idle_priority),
        nice_increment=_sandbox_int("nice_increment", mac_defaults.nice_increment),
        collect_usage=_sandbox_bool("collect_usage", mac_defaults.collect_usage),
    )
    sandbox = SandboxHarness(config=sandbox_config, permissions=sandbox_permissions)

    if pool_enabled:
        def _as_int(value: Any, default: int) -> int:
            try:
                return int(value) if value is not None else default
            except (TypeError, ValueError):
                return default

        def _as_float(value: Any, default: float) -> float:
            try:
                return float(value) if value is not None else default
            except (TypeError, ValueError):
                return default

        executable_raw = str(pool_settings.get("executable", "automation_daemon.py"))
        executable_path = Path(executable_raw)
        if not executable_path.is_absolute():
            executable_path = Path(__file__).resolve().parents[0] / executable_path
        min_runtimes = _as_int(pool_settings.get("min_runtimes"), 0)
        max_runtimes = _as_int(pool_settings.get("max_runtimes"), 1)
        desired_default = min_runtimes if min_runtimes > 0 else 0
        desired_runtimes = _as_int(pool_settings.get("desired_runtimes"), desired_default)
        pool_config = PoolConfig(
            min_runtimes=min_runtimes,
            max_runtimes=max_runtimes,
            desired_runtimes=desired_runtimes,
            base_port=_as_int(pool_settings.get("base_port"), 9600),
            heartbeat_interval=_as_float(pool_settings.get("heartbeat_seconds"), 5.0),
            restart_backoff=_as_float(pool_settings.get("restart_backoff"), 3.0),
            shutdown_timeout=_as_float(pool_settings.get("shutdown_timeout"), 5.0),
        )
        try:
            runtime_pool = RuntimePool(executable=executable_path, gateway=gateway, config=pool_config)
            runtime_pool.start()
            runtime_pool.heartbeat()
            runtime_pool_config = pool_config
            pool_monitor_stop = threading.Event()
            monitor_stop = pool_monitor_stop
            monitor_pool = runtime_pool

            def _pool_monitor() -> None:
                interval = max(1.0, float(pool_config.heartbeat_interval))
                while not monitor_stop.wait(interval):
                    try:
                        monitor_pool.heartbeat()
                    except Exception as exc:
                        print(f"[daemon] Runtime pool heartbeat error: {exc}", file=sys.stderr)

            pool_monitor_thread = threading.Thread(target=_pool_monitor, name="runtime-pool-monitor", daemon=True)
            pool_monitor_thread.start()
        except Exception as exc:
            print(f"[daemon] Failed to start runtime pool: {exc}", file=sys.stderr)
            runtime_pool = None
            runtime_pool_config = None
            pool_monitor_stop = None
            pool_monitor_thread = None

    try:
        flask_server.start()
        grpc_server.start()
        gateway_server.start()
    except Exception:
        # Attempt to clean up partially started servers before propagating the error.
        try:
            flask_server.shutdown()
        finally:
            try:
                gateway_server.stop()
            finally:
                grpc_server.stop(grace=0)
        raise

    print(f"MLX runtime listening http://{mlx_host}:{actual_mlx_port}")
    print(f"gRPC server listening {grpc_host}:{bound_grpc_port}")
    print(f"Gateway HTTP listening {gateway_server.http_url}")
    print(f"Gateway WebSocket listening {gateway_server.ws_url}")
    print(f"Gateway IPC socket {gateway_server.ipc_path}")
    if gateway_server.bootstrap_token:
        message = f"Gateway bootstrap token {gateway_server.bootstrap_token}"
        if minted_bootstrap:
            message += " (newly generated; store securely)."
        print(message)

    return DaemonHandle(
        grpc_server=grpc_server,
        flask_server=flask_server,
        grpc_host=grpc_host,
        grpc_port=bound_grpc_port,
        mlx_host=mlx_host,
        mlx_port=actual_mlx_port,
        gateway_server=gateway_server,
        gateway=gateway,
        stop_event=stop_event,
        started_at=started_at,
        runtime_pool=runtime_pool,
        pool_config=runtime_pool_config,
        pool_monitor_stop=pool_monitor_stop,
        pool_monitor_thread=pool_monitor_thread,
        document_counter=_document_counter,
        metrics_provider=_metrics_provider,
        sandbox=sandbox,
        auth_manager=auth_manager,
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    stop_event = threading.Event()

    handle = start_daemon(
        grpc_host=args.grpc_host,
        grpc_port=args.grpc_port,
        mlx_host=args.mlx_host,
        mlx_port=args.mlx_port,
        models_dir=args.models_dir,
        stop_event=stop_event,
    )

    def _handle_signal(signum, frame):  # type: ignore[unused-argument]
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not handle.wait(timeout=0.5):
            pass
    finally:
        handle.stop()

    return 0


def _sync_runtime_url(host: str, port: int) -> None:
    url = f"http://{host}:{port}"
    config = get_config()
    model_cfg = config.setdefault("model", {})
    if model_cfg.get("runtime_url") == url:
        return
    model_cfg["runtime_url"] = url
    save_config(config)


if __name__ == "__main__":
    sys.exit(main())
