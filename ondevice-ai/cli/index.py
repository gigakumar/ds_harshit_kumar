"""Simple command-line helpers around the gRPC assistant service."""
from __future__ import annotations

import argparse
import json
import os
import textwrap
from typing import Any, Sequence, cast

import grpc  # type: ignore[import-untyped]

from core import assistant_pb2 as pb_module
from core import assistant_pb2_grpc as rpc
from core import config as core_config
from core.daemon_manager import (
    daemon_status as _daemon_status,
    restart_daemon as _restart_daemon,
    start_daemon as _start_daemon,
    stop_daemon as _stop_daemon,
)
from core.diagnostics import create_diagnostics_bundle

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


def _daemon_start(args: argparse.Namespace) -> None:
    extra_args: list[str] = []
    if args.grpc_port is not None:
        extra_args.extend(["--grpc-port", str(args.grpc_port)])
    if args.grpc_host is not None and args.grpc_host != "[::]":
        extra_args.extend(["--grpc-host", args.grpc_host])
    if args.mlx_port is not None:
        extra_args.extend(["--mlx-port", str(args.mlx_port)])
    if args.mlx_host is not None and args.mlx_host != "127.0.0.1":
        extra_args.extend(["--mlx-host", args.mlx_host])
    if args.models_dir:
        extra_args.extend(["--models-dir", args.models_dir])
    env = _build_override_env(args)
    status = _start_daemon(args=extra_args, env=env)
    print(_format_status(status))


def _daemon_stop(args: argparse.Namespace) -> None:  # noqa: ARG001
    status = _stop_daemon()
    print(_format_status(status))


def _daemon_restart(args: argparse.Namespace) -> None:
    extra_args: list[str] = []
    if args.grpc_port is not None:
        extra_args.extend(["--grpc-port", str(args.grpc_port)])
    if args.grpc_host is not None and args.grpc_host != "[::]":
        extra_args.extend(["--grpc-host", args.grpc_host])
    if args.mlx_port is not None:
        extra_args.extend(["--mlx-port", str(args.mlx_port)])
    if args.mlx_host is not None and args.mlx_host != "127.0.0.1":
        extra_args.extend(["--mlx-host", args.mlx_host])
    if args.models_dir:
        extra_args.extend(["--models-dir", args.models_dir])
    env = _build_override_env(args)
    status = _restart_daemon(args=extra_args, env=env)
    print(_format_status(status))


def _daemon_status_cmd(args: argparse.Namespace) -> None:  # noqa: ARG001
    status = _daemon_status()
    print(_format_status(status))


def _diagnostics_cmd(args: argparse.Namespace) -> None:
    bundle_path = create_diagnostics_bundle(
        output_path=args.output,
        include_logs=not args.no_logs,
        include_config=not args.no_config,
        include_plugins=not args.no_plugins,
        include_state_listing=not args.no_state_listing,
    )
    print(bundle_path)


def _format_status(status: Any) -> str:
    parts: list[str] = []
    if status.message:
        parts.append(status.message)
    if status.running and status.pid is not None:
        parts.append(f"pid={status.pid}")
    if status.running and status.uptime_seconds is not None:
        parts.append(f"uptime={int(status.uptime_seconds)}s")
    if status.running and getattr(status, "cmd", None):
        parts.append(f"cmd={status.cmd}")
    if getattr(status, "child_pid", None):
        parts.append(f"child_pid={status.child_pid}")
    if getattr(status, "restart_count", 0):
        parts.append(f"restarts={status.restart_count}")
    last_exit = getattr(status, "last_exit_code", None)
    if last_exit is not None and not status.running:
        parts.append(f"last_exit={last_exit}")
    last_pid = getattr(status, "pid", None)
    if not status.running and last_pid:
        parts.append(f"last_pid={last_pid}")
    health_status = getattr(status, "health_status", None)
    if health_status:
        parts.append(f"health_status={health_status}")
    health_url = getattr(status, "health_url", None)
    if health_url:
        parts.append(f"health={health_url}")
    joined = "; ".join(parts) if parts else ""
    return os.linesep.join(textwrap.wrap(joined)) if joined else ""


def _split_assignment(text: str) -> tuple[str, str]:
    if "=" not in text:
        raise SystemExit(f"Invalid override '{text}'. Expected KEY=VALUE format.")
    key, value = text.split("=", 1)
    key = key.strip()
    value = value.strip()
    if not key:
        raise SystemExit("Override key cannot be empty.")
    return key, value


def _normalize_override_path(raw: str) -> list[str]:
    tokens = [segment.strip() for segment in raw.split(".") if segment.strip()]
    if not tokens:
        raise SystemExit("Configuration path cannot be empty.")
    return [token.replace("-", "_").lower() for token in tokens]


def _assign_override(target: dict[str, Any], path: Sequence[str], value: Any) -> None:
    cursor: dict[str, Any] = target
    for token in path[:-1]:
        existing = cursor.setdefault(token, {})
        if not isinstance(existing, dict):
            raise SystemExit(f"Cannot assign override for {'.'.join(path)}; '{token}' is a non-mapping value.")
        cursor = existing
    cursor[path[-1]] = value


def _build_override_env(args: argparse.Namespace) -> dict[str, str] | None:
    env: dict[str, str] = {}
    regular: dict[str, Any] = {}
    secret: dict[str, Any] = {}

    for assignment in getattr(args, "config_set", []) or []:
        key_path, raw_value = _split_assignment(assignment)
        path_tokens = _normalize_override_path(key_path)
        value = core_config.parse_override_value(raw_value)
        _assign_override(regular, path_tokens, value)

    for assignment in getattr(args, "config_secret", []) or []:
        key_path, env_name = _split_assignment(assignment)
        env_value = os.environ.get(env_name)
        if env_value is None:
            raise SystemExit(f"Environment variable '{env_name}' is not set for secret override '{key_path}'.")
        path_tokens = _normalize_override_path(key_path)
        value = core_config.parse_override_value(env_value)
        _assign_override(secret, path_tokens, value)

    if getattr(args, "config", None):
        env["MAHI_CONFIG"] = args.config
    if regular:
        env["MAHI_CONFIG_OVERRIDES"] = json.dumps(regular)
    if secret:
        env["MAHI_SECRET_OVERRIDES"] = json.dumps(secret)

    return env or None


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

    daemon_cmd = sub.add_parser("daemon", help="Manage the local automation daemon")
    daemon_sub = daemon_cmd.add_subparsers(dest="daemon_command", required=True)

    def _add_daemon_common(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--grpc-host", default=None, help="Override daemon gRPC bind host")
        cmd.add_argument("--grpc-port", type=int, default=None, help="Override daemon gRPC port")
        cmd.add_argument("--mlx-host", default=None, help="Override daemon MLX HTTP host")
        cmd.add_argument("--mlx-port", type=int, default=None, help="Override daemon MLX HTTP port")
        cmd.add_argument("--models-dir", help="Custom models directory")
        cmd.add_argument("--config", help="Path to configuration file overrides")

    start_cmd = daemon_sub.add_parser("start", help="Start the local daemon in the background")
    _add_daemon_common(start_cmd)
    start_cmd.add_argument(
        "--set",
        dest="config_set",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="Override configuration path (dot notation). Repeat for multiple overrides.",
    )
    start_cmd.add_argument(
        "--secret",
        dest="config_secret",
        action="append",
        default=[],
        metavar="PATH=ENVVAR",
        help="Set configuration path using value from environment variable (for secrets).",
    )
    start_cmd.set_defaults(func=_daemon_start)

    stop_cmd = daemon_sub.add_parser("stop", help="Stop the local daemon")
    stop_cmd.set_defaults(func=_daemon_stop)

    restart_cmd = daemon_sub.add_parser("restart", help="Restart the local daemon")
    _add_daemon_common(restart_cmd)
    restart_cmd.add_argument(
        "--set",
        dest="config_set",
        action="append",
        default=[],
        metavar="PATH=VALUE",
        help="Override configuration path (dot notation). Repeat for multiple overrides.",
    )
    restart_cmd.add_argument(
        "--secret",
        dest="config_secret",
        action="append",
        default=[],
        metavar="PATH=ENVVAR",
        help="Set configuration path using value from environment variable (for secrets).",
    )
    restart_cmd.set_defaults(func=_daemon_restart)

    status_cmd = daemon_sub.add_parser("status", help="Check daemon status")
    status_cmd.set_defaults(func=_daemon_status_cmd)

    diagnostics_cmd = sub.add_parser("diagnostics", help="Collect a diagnostics support bundle")
    diagnostics_cmd.add_argument("--output", help="Destination zip file path")
    diagnostics_cmd.add_argument("--no-logs", action="store_true", help="Skip daemon log capture")
    diagnostics_cmd.add_argument("--no-config", action="store_true", help="Skip automation config capture")
    diagnostics_cmd.add_argument("--no-plugins", action="store_true", help="Skip copying plugin manifests")
    diagnostics_cmd.add_argument("--no-state-listing", action="store_true", help="Skip state directory listing")
    diagnostics_cmd.set_defaults(func=_diagnostics_cmd)

    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
