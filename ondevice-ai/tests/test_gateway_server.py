import json
import os
import tempfile
import time
import urllib.request
from typing import cast

import pytest

from core.auth import AuthManager, TokenStore
from core.gateway_server import GatewayServer, _extract_token_from_headers, _extract_token_from_query
from core.orchestrator import Orchestrator
from core.runtime_gateway import RuntimeGateway


class _StubStore:
    def __init__(self) -> None:
        self._count = 3

    def count_docs(self) -> int:
        return self._count


class _StubOrchestrator:
    def __init__(self) -> None:
        self.store = _StubStore()
        self.last_index: tuple[str, str] | None = None

    async def query(self, query: str, k: int) -> list[dict[str, object]]:
        return [{"doc_id": "1", "score": 0.9, "text": f"echo:{query}"}]

    async def index_text(self, text: str, source: str) -> str:
        self.last_index = (text, source)
        return "doc-1"

    async def plan(self, goal: str, params=None):
        return [{"name": "step", "payload": goal, "sensitive": False, "preview_required": False}]


def _post_json(url: str, payload: dict[str, object], token: str) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def test_token_extraction_helpers() -> None:
    headers = {"Authorization": "Bearer abc123"}
    assert _extract_token_from_headers(headers) == "abc123"
    headers = {"X-Mahi-Token": "xyz"}
    assert _extract_token_from_headers(headers) == "xyz"
    assert _extract_token_from_headers({}) == ""

    assert _extract_token_from_query("/socket?token=abc") == "abc"
    assert _extract_token_from_query("/socket") == ""


@pytest.mark.skipif(os.name != "posix", reason="IPC sockets require POSIX")
def test_gateway_http_endpoints_round_trip() -> None:
    orchestrator = _StubOrchestrator()
    gateway = RuntimeGateway()
    auth_manager = AuthManager(
        store=TokenStore(backend="memory"),
        bootstrap_token=None,
        default_ttl=0,
        rate_limit_per_minute=1000,
    )
    metrics = {"uptime_seconds": 0.0}
    server = GatewayServer(
        orchestrator=cast(Orchestrator, orchestrator),
        gateway=gateway,
        metrics_provider=lambda: metrics,
        auth_manager=auth_manager,
        http_port=0,
        ws_port=0,
        ipc_path=tempfile.mktemp(prefix="mahi-gateway-"),
    )
    server.start()
    try:
        token = server.bootstrap_token
        assert token is not None

        # Allow the HTTP server to bind before issuing requests.
        time.sleep(0.05)
        query_response = _post_json(f"{server.http_url}/v1/query", {"query": "hello", "k": 1}, token)
        hits = cast(list[dict[str, object]], query_response.get("hits", []))
        assert hits and hits[0]["text"] == "echo:hello"

        index_response = _post_json(
            f"{server.http_url}/v1/index",
            {"text": "new doc", "source": "test"},
            token,
        )
        assert index_response["doc_id"] == "doc-1"
        assert orchestrator.last_index == ("new doc", "test")

        status_request = urllib.request.Request(
            f"{server.http_url}/v1/status",
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        with urllib.request.urlopen(status_request, timeout=5) as response:
            status_body = json.loads(response.read().decode("utf-8"))
        assert status_body["metrics"] == metrics
        assert "gateway" in status_body
    finally:
        server.stop()
        try:
            if os.path.exists(server.ipc_path):
                os.unlink(server.ipc_path)
        except OSError:
            pass
