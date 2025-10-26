"""Helper functions executed inside sandbox tests."""
from __future__ import annotations

import socket
import time
from pathlib import Path


def add_numbers(a: int, b: int) -> int:
    return a + b


def attempt_socket_connection() -> None:
    sock = socket.socket()  # type: ignore[call-arg]
    try:
        sock.connect(("example.com", 80))
    finally:
        try:
            sock.close()
        except Exception:
            pass


def write_file(filename: str, text: str) -> str:
    path = Path(filename)
    path.write_text(text)
    return path.read_text()


def slow_operation(seconds: float) -> str:
    time.sleep(seconds)
    return "done"
