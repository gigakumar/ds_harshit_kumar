# core/server.py
from __future__ import annotations

import asyncio
import json
import threading
from concurrent import futures
from typing import Any, Coroutine, Iterable, cast

import grpc

from core import assistant_pb2 as pb_module
from core import assistant_pb2_grpc as rpc
from core.audit import write_event
from core.orchestrator import Orchestrator

pb = cast(Any, pb_module)


_LOOP = asyncio.new_event_loop()
_THREAD = threading.Thread(target=_LOOP.run_forever, name="grpc-worker-loop", daemon=True)
_THREAD.start()


def _run(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run the orchestrator coroutine on the shared background loop."""
    return asyncio.run_coroutine_threadsafe(coro, _LOOP).result()


class AssistantServicer(rpc.AssistantServicer):
    """Blocking gRPC façade over the async orchestrator."""

    def __init__(self, orchestrator: Orchestrator | None = None) -> None:
        self._orchestrator = orchestrator or Orchestrator()

    def IndexText(self, request, context):
        doc_id = _run(self._orchestrator.index_text(request.text, request.source or "grpc"))
        return pb.IndexResponse(id=request.id, doc_id=doc_id, status=0)

    def Query(self, request, context):
        hits = _run(self._orchestrator.query(request.query, request.k or 5))
        response = pb.QueryResponse(id=request.id)
        for hit in hits:
            response.hits.add(doc_id=str(hit["doc_id"]), score=float(hit["score"] or 0.0), text=hit.get("text", ""))
        return response

    def Plan(self, request, context):
        actions = _run(self._orchestrator.plan(request.goal))
        response = pb.PlanResponse(id=request.id)
        for action in _normalize_actions(actions):
            target = response.actions.add()
            target.name = action.get("name", "")
            target.payload = action.get("payload", "")
            target.sensitive = bool(action.get("sensitive", False))
            target.preview_required = bool(action.get("preview_required", False))
        return response

    def ExecuteAction(self, request, context):
        payload = _safe_parse_json(request.payload)
        write_event(
            {
                "type": "action_execute",
                "name": request.name,
                "payload": payload,
                "sensitive": bool(request.sensitive),
                "preview_required": bool(request.preview_required),
            }
        )
        return pb.IndexResponse(id="", doc_id=request.name, status=0)


def _normalize_actions(actions: Iterable[Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in actions or []:
        if isinstance(item, dict):
            normalized.append(dict(item))
        else:
            normalized.append({"name": str(item)})
    return normalized


def _safe_parse_json(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"raw": raw}


def create_server(host: str = "[::]", port: int = 50051, orchestrator: Orchestrator | None = None) -> grpc.Server:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=8))
    rpc.add_AssistantServicer_to_server(AssistantServicer(orchestrator=orchestrator), server)
    requested_address = f"{host}:{port}"
    bound_port = server.add_insecure_port(requested_address)
    if bound_port == 0:
        if port != 0:
            fallback_address = f"{host}:0"
            bound_port = server.add_insecure_port(fallback_address)
    if bound_port == 0:
        raise RuntimeError(f"Failed to bind gRPC server on {requested_address}")
    setattr(server, "_bound_port", bound_port)
    return server


def serve(host: str = "[::]", port: int = 50051) -> None:
    server = create_server(host=host, port=port)
    server.start()
    bound_port = getattr(server, "_bound_port", port)
    print(f"gRPC server listening {host}:{bound_port}")
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=None)


__all__ = ["create_server", "serve"]


if __name__ == "__main__":
    serve()
