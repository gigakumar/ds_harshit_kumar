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
from typing import Any, Optional

from core.config import get_config, save_config
from core.server import create_server
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
    stop_event: threading.Event
    _stopped: bool = False

    def stop(self) -> None:
        if self._stopped:
            return
        try:
            self.grpc_server.stop(grace=0)
        finally:
            try:
                self.flask_server.shutdown()
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

    flask_server = _FlaskServer(host=mlx_host, port=mlx_port)
    actual_mlx_port = flask_server.port
    _sync_runtime_url(mlx_host, actual_mlx_port)

    grpc_server = create_server(host=grpc_host, port=grpc_port)
    bound_grpc_port = getattr(grpc_server, "_bound_port", grpc_port)

    try:
        flask_server.start()
        grpc_server.start()
    except Exception:
        # Attempt to clean up partially started servers before propagating the error.
        try:
            flask_server.shutdown()
        finally:
            grpc_server.stop(grace=0)
        raise

    print(f"MLX runtime listening http://{mlx_host}:{actual_mlx_port}")
    print(f"gRPC server listening {grpc_host}:{bound_grpc_port}")

    return DaemonHandle(
        grpc_server=grpc_server,
        flask_server=flask_server,
        grpc_host=grpc_host,
        grpc_port=bound_grpc_port,
        mlx_host=mlx_host,
        mlx_port=actual_mlx_port,
        stop_event=stop_event,
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
