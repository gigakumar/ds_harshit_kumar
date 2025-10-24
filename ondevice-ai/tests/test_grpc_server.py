import json
import socket
import time
from typing import Any, cast

import grpc

from core import assistant_pb2 as pb_module
from core import assistant_pb2_grpc as rpc
from core.orchestrator import Orchestrator
from core.server import create_server
from core.vector_store import VectorStore


pb = cast(Any, pb_module)


class StubModel:
    async def embed(self, texts):
        return [[1.0, 0.5, 0.25, 0.125] for _ in texts]

    async def predict(self, prompt, params=None):
        return json.dumps([
            {"name": "demo", "payload": json.dumps({"prompt": prompt}), "sensitive": False, "preview_required": False}
        ])


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_grpc_round_trip(tmp_path):
    port = _free_port()
    orchestrator = Orchestrator(store=VectorStore(path=str(tmp_path / "grpc.db")), model=StubModel())
    server = create_server(host="127.0.0.1", port=port, orchestrator=orchestrator)
    server.start()
    try:
        time.sleep(0.1)
        channel = grpc.insecure_channel(f"127.0.0.1:{port}")
        stub = rpc.AssistantStub(channel)

        index_resp = stub.IndexText(pb.IndexRequest(id="idx", user_id="u", text="hello", source="test"))
        assert index_resp.doc_id

        query_resp = stub.Query(pb.QueryRequest(id="query", user_id="u", query="hello", k=3))
        assert query_resp.hits

        plan_resp = stub.Plan(pb.PlanRequest(id="plan", user_id="u", goal="demo goal"))
        assert plan_resp.actions and plan_resp.actions[0].name == "demo"

    finally:
        server.stop(grace=0)