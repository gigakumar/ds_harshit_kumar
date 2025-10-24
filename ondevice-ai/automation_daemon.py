#!/usr/bin/env python
"""Automation daemon that hosts the gRPC orchestrator service and MLX runtime."""
from __future__ import annotations

import argparse
import os
import signal
import sys
import threading
import time
from typing import Optional

from core.server import create_server
from tools.mlx_runtime import app as mlx_app
from werkzeug.serving import make_server


class _FlaskServer(threading.Thread):
    def __init__(self, host: str, port: int):
        super().__init__(daemon=True)
        self._host = host
        self._port = port
        self._server = make_server(host, port, mlx_app)
        self._ctx = mlx_app.app_context()

    def run(self) -> None:
        self._ctx.push()
        try:
            self._server.serve_forever()
        finally:
            self._ctx.pop()

    def shutdown(self) -> None:
        self._server.shutdown()


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Launch the automation daemon.")
    parser.add_argument("--grpc-host", default="[::]", help="Host/interface for gRPC server")
    parser.add_argument("--grpc-port", type=int, default=50051, help="Port for gRPC server")
    parser.add_argument("--mlx-host", default="127.0.0.1", help="Host/interface for MLX HTTP runtime")
    parser.add_argument("--mlx-port", type=int, default=9000, help="Port for MLX HTTP runtime")
    parser.add_argument("--models-dir", help="Override ML models directory", default=None)
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)

    if args.models_dir:
        os.environ["ML_MODELS_DIR"] = os.path.abspath(args.models_dir)

    flask_server = _FlaskServer(host=args.mlx_host, port=args.mlx_port)
    flask_server.start()

    grpc_server = create_server(host=args.grpc_host, port=args.grpc_port)
    grpc_server.start()

    print(f"MLX runtime listening http://{args.mlx_host}:{args.mlx_port}")
    print(f"gRPC server listening {args.grpc_host}:{args.grpc_port}")

    stop_event = threading.Event()

    def _handle_signal(signum, frame):  # type: ignore[unused-argument]
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not stop_event.is_set():
            time.sleep(0.5)
    finally:
        grpc_server.stop(grace=0)
        flask_server.shutdown()

    return 0


if __name__ == "__main__":
    sys.exit(main())
