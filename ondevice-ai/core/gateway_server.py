"""Multi-protocol gateway that exposes orchestrator operations across transports."""
from __future__ import annotations

import asyncio
import contextlib
import json
import threading
import time
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Coroutine, Optional
from urllib.parse import parse_qs, urlparse

from flask import Flask, jsonify, request
from werkzeug.serving import make_server

try:  # pragma: no cover - optional dependency pulled in via requirements
    import websockets  # type: ignore[import-not-found]
except Exception as exc:  # pragma: no cover - fallback if dependency missing
    raise RuntimeError("websockets package is required for GatewayServer") from exc

from core.auth import AuthManager, TokenMetadata
from core.orchestrator import Orchestrator
from core.runtime_gateway import RuntimeEndpoint, RuntimeGateway


MetricsProvider = Callable[[], dict[str, Any]]


class GatewayServer:
    """Coordinates HTTP, WebSocket, and local IPC access to the orchestrator."""

    def __init__(
        self,
        orchestrator: Orchestrator,
        gateway: RuntimeGateway,
        *,
        auth_manager: AuthManager,
        metrics_provider: Optional[MetricsProvider] = None,
        http_host: str = "127.0.0.1",
        http_port: int = 8710,
        ws_host: str = "127.0.0.1",
        ws_port: int = 8711,
        ipc_path: Optional[str] = None,
    ) -> None:
        self._orchestrator = orchestrator
        self._gateway = gateway
        self._auth_manager = auth_manager
        self._metrics_provider = metrics_provider or (lambda: {})
        self._http_host = http_host
        self._http_port = http_port
        self._http_server = None
        self._http_thread: Optional[threading.Thread] = None
        self._actual_http_port = http_port

        self._ws_host = ws_host
        self._ws_port = ws_port
        self._ws_server: Any = None
        self._actual_ws_port = ws_port

        self._ipc_path = Path(ipc_path or _default_ipc_path())
        self._ipc_server: Optional[asyncio.AbstractServer] = None

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[threading.Thread] = None

        self._bootstrap_token: Optional[TokenMetadata] = None
        self._running = False
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True

        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self._loop.run_forever, daemon=True, name="gateway-loop")
        self._loop_thread.start()

        self._bootstrap_token = self._auth_manager.ensure_bootstrap_token()

        self._start_http()
        self._start_ws()
        self._start_ipc()

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._running = False

        if self._http_server is not None:
            self._http_server.shutdown()
            self._http_server = None
        if self._http_thread is not None:
            self._http_thread.join(timeout=2.0)
            self._http_thread = None

        if self._loop is not None:
            if self._ws_server is not None:
                async def _close_ws(server: Any) -> None:
                    server.close()
                    await server.wait_closed()

                asyncio.run_coroutine_threadsafe(_close_ws(self._ws_server), self._loop).result(timeout=5.0)
                self._ws_server = None
            if self._ipc_server is not None:
                async def _close_ipc(server: asyncio.AbstractServer) -> None:
                    server.close()
                    await server.wait_closed()

                asyncio.run_coroutine_threadsafe(_close_ipc(self._ipc_server), self._loop).result(timeout=5.0)
                self._ipc_server = None
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread is not None:
                self._loop_thread.join(timeout=2.0)
            self._loop = None
            self._loop_thread = None

        try:
            if self._ipc_path.exists():
                self._ipc_path.unlink()
        except Exception:
            pass

    # ------------------------------------------------------------------
    @property
    def bootstrap_token(self) -> Optional[str]:
        return self._bootstrap_token.token if self._bootstrap_token else None

    @property
    def http_url(self) -> str:
        return f"http://{self._http_host}:{self._actual_http_port}"

    @property
    def ws_url(self) -> str:
        return f"ws://{self._ws_host}:{self._actual_ws_port}"

    @property
    def ipc_path(self) -> str:
        return str(self._ipc_path)

    # ------------------------------------------------------------------
    def _authorize_token(self, token: str, *, scope: Optional[str]) -> Optional[TokenMetadata]:
        if not token:
            return None
        metadata = self._auth_manager.validate(token, scope=scope)
        if metadata is None:
            return None
        try:
            self._auth_manager.record_usage(token)
        except PermissionError:
            raise
        return metadata

    # ------------------------------------------------------------------
    def _start_http(self) -> None:
        app = self._build_http_app()
        server = make_server(self._http_host, self._http_port, app)
        self._actual_http_port = int(getattr(server, "server_port", self._http_port))
        self._http_server = server
        self._http_thread = threading.Thread(target=server.serve_forever, daemon=True, name="gateway-http")
        self._http_thread.start()
        self._gateway.register(
            RuntimeEndpoint(
                name="gateway-http",
                protocol="http",
                address=self.http_url,
                metadata={"token_required": True},
            )
        )

    def _start_ws(self) -> None:
        if self._loop is None:
            raise RuntimeError("Gateway loop not initialized")
        async def _create_ws() -> Any:
            return await websockets.serve(self._ws_handler, self._ws_host, self._ws_port)  # type: ignore[arg-type]

        self._ws_server = asyncio.run_coroutine_threadsafe(_create_ws(), self._loop).result(timeout=5.0)
        server = self._ws_server
        if server is None:
            return
        sockets = server.sockets or []
        if sockets:
            sock = sockets[0]
            if isinstance(sock.getsockname(), tuple):
                self._actual_ws_port = int(sock.getsockname()[1])
        self._gateway.register(
            RuntimeEndpoint(
                name="gateway-ws",
                protocol="ws",
                address=self.ws_url,
                metadata={"token_required": True},
            )
        )

    def _start_ipc(self) -> None:
        if self._loop is None:
            raise RuntimeError("Gateway loop not initialized")
        try:
            if self._ipc_path.exists():
                self._ipc_path.unlink()
        except Exception:
            pass

        self._ipc_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            ipc_coro = asyncio.start_unix_server(self._ipc_handler, path=self._ipc_path)
            self._ipc_server = asyncio.run_coroutine_threadsafe(ipc_coro, self._loop).result(timeout=5.0)
        except (AttributeError, NotImplementedError, OSError):
            return
        self._gateway.register(
            RuntimeEndpoint(
                name="gateway-ipc",
                protocol="ipc",
                address=str(self._ipc_path),
                metadata={"token_required": True},
            )
        )

    # ------------------------------------------------------------------
    def _build_http_app(self) -> Flask:
        app = Flask("mahi-gateway")

        def require_scope(scope: Optional[str]):
            def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
                @wraps(func)
                def wrapper(*args: Any, **kwargs: Any):
                    token = _extract_token_from_headers(dict(request.headers))
                    try:
                        metadata = self._authorize_token(token, scope=scope)
                    except PermissionError:
                        return jsonify({"error": "rate_limit_exceeded"}), 429
                    if metadata is None:
                        return jsonify({"error": "unauthorized"}), 401
                    return func(*args, **kwargs)

                return wrapper

            return decorator

        @app.get("/v1/status")
        @require_scope("status")
        def status_endpoint() -> Any:
            metrics = self._metrics_provider()
            return jsonify({"metrics": metrics, "gateway": self._gateway.snapshot()})

        @app.post("/v1/query")
        @require_scope("query")
        def query_endpoint() -> Any:
            payload = request.get_json(silent=True) or {}
            query = str(payload.get("query", "")).strip()
            top_k = int(payload.get("k", 5) or 5)
            if not query:
                return jsonify({"error": "query required"}), 400
            hits = self._run_async(self._orchestrator.query(query, top_k))
            return jsonify({"hits": hits})

        @app.post("/v1/index")
        @require_scope("index")
        def index_endpoint() -> Any:
            payload = request.get_json(silent=True) or {}
            text = str(payload.get("text", "")).strip()
            source = str(payload.get("source", "http")).strip() or "http"
            if not text:
                return jsonify({"error": "text required"}), 400
            doc_id = self._run_async(self._orchestrator.index_text(text, source))
            return jsonify({"doc_id": doc_id})

        @app.post("/v1/plan")
        @require_scope("plan")
        def plan_endpoint() -> Any:
            payload = request.get_json(silent=True) or {}
            goal = str(payload.get("goal", "")).strip()
            if not goal:
                return jsonify({"error": "goal required"}), 400
            params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
            actions = self._run_async(self._orchestrator.plan(goal, params=params))
            return jsonify({"actions": actions})

        return app

    # ------------------------------------------------------------------
    async def _ws_handler(self, websocket: Any) -> None:
        path = getattr(websocket, "path", "")
        token = _extract_token_from_query(path)
        try:
            metadata = self._authorize_token(token, scope="stream")
        except PermissionError:
            await websocket.close(code=4429, reason="rate_limit")
            return
        if metadata is None:
            await websocket.close(code=4401, reason="unauthorized")
            return

        await websocket.send(json.dumps({"type": "ready", "message": "gateway online"}))
        async for raw in websocket:
            try:
                payload = json.loads(raw)
            except Exception:
                await websocket.send(json.dumps({"type": "error", "error": "invalid_json"}))
                continue

            action = str(payload.get("action", "")).lower()
            if action == "ping":
                await websocket.send(json.dumps({"type": "pong", "ts": time.time()}))
                continue
            if action == "query":
                query = str(payload.get("query", "")).strip()
                k = int(payload.get("k", 5) or 5)
                if not query:
                    await websocket.send(json.dumps({"type": "error", "error": "query required"}))
                    continue
                hits = await self._orchestrator.query(query, k)
                await websocket.send(json.dumps({"type": "query_result", "hits": hits}))
                continue
            if action == "status":
                await websocket.send(json.dumps({"type": "status", "metrics": self._metrics_provider()}))
                continue
            if action == "plan":
                goal = str(payload.get("goal", "")).strip()
                params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
                if not goal:
                    await websocket.send(json.dumps({"type": "error", "error": "goal required"}))
                    continue
                actions = await self._orchestrator.plan(goal, params=params)
                await websocket.send(json.dumps({"type": "plan_result", "actions": actions}))
                continue
            await websocket.send(json.dumps({"type": "error", "error": "unsupported_action"}))

    async def _ipc_handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            token_line = await reader.readline()
            token = token_line.decode().strip()
            try:
                metadata = self._authorize_token(token, scope=None)
            except PermissionError:
                writer.write(b"{\"error\": \"rate_limit_exceeded\"}\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            if metadata is None:
                writer.write(b"{\"error\": \"unauthorized\"}\n")
                await writer.drain()
                writer.close()
                await writer.wait_closed()
                return
            while not reader.at_eof():
                line = await reader.readline()
                if not line:
                    break
                try:
                    payload = json.loads(line.decode())
                except Exception:
                    writer.write(b"{\"error\": \"invalid_json\"}\n")
                    await writer.drain()
                    continue
                action = str(payload.get("action", "")).lower()
                if action == "status":
                    response = {"metrics": self._metrics_provider(), "gateway": self._gateway.snapshot()}
                elif action == "query":
                    query = str(payload.get("query", "")).strip()
                    k = int(payload.get("k", 5) or 5)
                    if not query:
                        response = {"error": "query required"}
                    else:
                        hits = await self._orchestrator.query(query, k)
                        response = {"hits": hits}
                elif action == "plan":
                    goal = str(payload.get("goal", "")).strip()
                    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
                    if not goal:
                        response = {"error": "goal required"}
                    else:
                        actions = await self._orchestrator.plan(goal, params=params)
                        response = {"actions": actions}
                else:
                    response = {"error": "unsupported_action"}
                writer.write(json.dumps(response).encode("utf-8") + b"\n")
                await writer.drain()
        finally:
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()

    # ------------------------------------------------------------------
    def _run_async(self, coro: Coroutine[Any, Any, Any]) -> Any:
        if self._loop is None:
            return asyncio.run(coro)
        return asyncio.run_coroutine_threadsafe(coro, self._loop).result(timeout=30.0)


def _extract_token_from_headers(headers: dict[str, Any]) -> str:
    auth = str(headers.get("Authorization", ""))
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    token = headers.get("X-Mahi-Token")
    if token:
        return str(token).strip()
    return ""


def _extract_token_from_query(path: str) -> str:
    parsed = urlparse(path or "/")
    params = parse_qs(parsed.query)
    token_values = params.get("token")
    if token_values:
        return str(token_values[0]).strip()
    return ""


def _default_ipc_path() -> str:
    runtime_dir = Path.home() / ".mahi" / "sockets"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return str(runtime_dir / "gateway.sock")
