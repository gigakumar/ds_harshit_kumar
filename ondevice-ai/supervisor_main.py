"""Entry point for the daemon supervisor."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core import config as core_config
from core.supervisor import Supervisor, SupervisorConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the automation daemon under supervision.")
    parser.add_argument("--log-file", required=True, help="File to append supervisor and child logs to.")
    parser.add_argument("--state-file", required=True, help="File used to persist supervisor state metadata.")
    parser.add_argument("--max-restarts", type=int, help="Maximum restarts permitted within window.")
    parser.add_argument("--window-seconds", type=float, help="Sliding window for restart budget.")
    parser.add_argument("--backoff-seconds", type=float, help="Initial backoff delay before restart.")
    parser.add_argument("--max-backoff-seconds", type=float, help="Maximum backoff delay between restarts.")
    parser.add_argument("--graceful-shutdown-seconds", type=float, help="Grace period before force killing child.")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="Command to supervise (precede with --).")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = [arg for arg in args.command if arg != "--"]
    if not command:
        parser.error("No command provided for supervision.")

    config_map = core_config.get_config().get("supervisor")
    supervisor_cfg = SupervisorConfig.from_mapping(config_map if isinstance(config_map, dict) else None)

    # Allow CLI overrides to take precedence.
    if args.max_restarts is not None:
        supervisor_cfg.max_restarts = args.max_restarts
    if args.window_seconds is not None:
        supervisor_cfg.window_seconds = args.window_seconds
    if args.backoff_seconds is not None:
        supervisor_cfg.backoff_seconds = args.backoff_seconds
    if args.max_backoff_seconds is not None:
        supervisor_cfg.max_backoff_seconds = args.max_backoff_seconds
    if args.graceful_shutdown_seconds is not None:
        supervisor_cfg.graceful_shutdown_seconds = args.graceful_shutdown_seconds

    supervisor = Supervisor(
        command,
        log_path=Path(args.log_file).expanduser().resolve(),
        state_file=Path(args.state_file).expanduser().resolve(),
        config=supervisor_cfg,
    )
    return supervisor.run()


if __name__ == "__main__":  # pragma: no cover - script entry point
    sys.exit(main())
