"""Simple command-line helpers around the gRPC assistant service."""
from __future__ import annotations

import argparse
import json
from typing import Any, Sequence, cast

import grpc  # type: ignore[import-untyped]

from core import assistant_pb2 as pb_module
from core import assistant_pb2_grpc as rpc

pb = cast(Any, pb_module)


def _create_stub(target: str) -> rpc.AssistantStub:
    channel = grpc.insecure_channel(target)
    return rpc.AssistantStub(channel)


def _handle_rpc_error(exc: grpc.RpcError) -> None:
    detail = exc.details() or "unknown"
    if "decompressing data" in detail or "Connect" in detail:
        message = (
            "Unable to reach the automation daemon. "
            "Start it first with `python automation_daemon.py` (leave it running) "
            "or use the packaged app, then retry."
        )
    else:
        message = f"gRPC call failed: {detail}"
    raise SystemExit(message) from exc


def _index(args: argparse.Namespace) -> None:
    stub = _create_stub(args.target)
    response = None
    try:
        response = stub.IndexText(
            pb.IndexRequest(
                id=args.request_id,
                user_id=args.user_id,
                text=args.text,
                source=args.source,
                ts=0,
            )
        )
    except grpc.RpcError as exc:  # pragma: no cover - network/runtime failures
        _handle_rpc_error(exc)
    if response is None:  # pragma: no cover - defensive
        return
    print(response.doc_id)


def _query(args: argparse.Namespace) -> None:
    stub = _create_stub(args.target)
    response = None
    try:
        response = stub.Query(
            pb.QueryRequest(
                id=args.request_id,
                user_id=args.user_id,
                query=args.query,
                k=args.limit,
            )
        )
    except grpc.RpcError as exc:  # pragma: no cover
        _handle_rpc_error(exc)
    if response is None:  # pragma: no cover
        return
    for hit in response.hits:
        print(json.dumps({"doc_id": hit.doc_id, "score": hit.score, "text": hit.text}))


def _plan(args: argparse.Namespace) -> None:
    stub = _create_stub(args.target)
    response = None
    try:
        response = stub.Plan(
            pb.PlanRequest(
                id=args.request_id,
                user_id=args.user_id,
                goal=args.goal,
            )
        )
    except grpc.RpcError as exc:  # pragma: no cover
        _handle_rpc_error(exc)
    if response is None:  # pragma: no cover
        return
    for action in response.actions:
        print(json.dumps({
            "name": action.name,
            "payload": action.payload,
            "sensitive": action.sensitive,
            "preview_required": action.preview_required,
        }))


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--target", default="localhost:50051", help="gRPC host:port")
    parser.add_argument("--user-id", default="cli", help="User identifier")
    parser.add_argument("--request-id", default="req-1", help="Request identifier")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interact with the local automation assistant.")
    sub = parser.add_subparsers(dest="command", required=True)

    index_cmd = sub.add_parser("index", help="Index raw text into the knowledge store")
    _add_common_arguments(index_cmd)
    index_cmd.add_argument("text", help="Plain text to index")
    index_cmd.add_argument("--source", default="cli", help="Optional document source tag")
    index_cmd.set_defaults(func=_index)

    query_cmd = sub.add_parser("query", help="Run a semantic search query")
    _add_common_arguments(query_cmd)
    query_cmd.add_argument("query", help="Query text")
    query_cmd.add_argument("--limit", type=int, default=5, help="Maximum number of hits")
    query_cmd.set_defaults(func=_query)

    plan_cmd = sub.add_parser("plan", help="Ask the assistant to propose a plan")
    _add_common_arguments(plan_cmd)
    plan_cmd.add_argument("goal", help="Natural language goal")
    plan_cmd.set_defaults(func=_plan)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
