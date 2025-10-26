"""Diagnostics bundle exporter for support and debugging."""
from __future__ import annotations

import json
import os
import platform
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional

import psutil  # type: ignore[import-untyped]

from . import config
from . import daemon_manager

_ENV_SNAPSHOT_KEYS: tuple[str, ...] = (
    "MAHI_CONFIG",
    "MAHI_STATE_DIR",
    "ML_MODELS_DIR",
    "PYTHONPATH",
)


def _copy_if_exists(source: Path, destination_dir: Path, *, rename: str | None = None) -> None:
    if not source.exists():
        return
    destination_dir.mkdir(parents=True, exist_ok=True)
    target = destination_dir / (rename or source.name)
    shutil.copy2(source, target)


def _gather_environment(env: Mapping[str, str]) -> Mapping[str, str]:
    snapshot: dict[str, str] = {}
    for key in _ENV_SNAPSHOT_KEYS:
        if key in env:
            snapshot[key] = env[key]
    return snapshot


def _diagnostics_metadata(state_dir: Path | None = None) -> dict[str, object]:
    status = daemon_manager.daemon_status(state_dir=state_dir)
    metadata: dict[str, object] = {
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python": sys.version,
        "psutil_version": getattr(psutil, "__version__", "unknown"),
        "daemon": {
            "running": status.running,
            "pid": status.pid,
            "uptime_seconds": status.uptime_seconds,
            "message": status.message,
        },
        "environment": _gather_environment(os.environ),
    }
    try:
        boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
        metadata["system"] = {
            "boot_time": boot_time.isoformat(),
            "cpu_count": psutil.cpu_count(logical=True),
            "memory": psutil.virtual_memory()._asdict(),
        }
    except Exception:
        metadata.setdefault("system", {})
    return metadata


def _copy_directory_contents(sources: Iterable[Path], destination: Path) -> None:
    for source in sources:
        if not source.exists():
            continue
        if source.is_file():
            _copy_if_exists(source, destination)
        else:
            for path in source.rglob("*"):
                if path.is_file():
                    relative = path.relative_to(source)
                    target_dir = destination / source.name / relative.parent
                    target_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(path, target_dir / relative.name)


def create_diagnostics_bundle(
    output_path: Optional[Path | str] = None,
    *,
    include_logs: bool = True,
    include_config: bool = True,
    include_plugins: bool = True,
    include_state_listing: bool = True,
    state_dir: Path | None = None,
) -> Path:
    """Create a zip archive containing diagnostic artifacts."""
    state_path = daemon_manager.state_directory(state_dir)
    diagnostics_root = state_path / "diagnostics"
    diagnostics_root.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d-%H%M%S")
    if output_path is None:
        bundle_path = diagnostics_root / f"mahi-diagnostics-{timestamp}.zip"
    else:
        bundle_path = Path(output_path).expanduser().resolve()
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        if bundle_path.suffix != ".zip":
            bundle_path = bundle_path.with_suffix(".zip")

    with tempfile.TemporaryDirectory() as tmpdir:
        staging_root = Path(tmpdir)
        artifacts_dir = staging_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # Metadata summary
        metadata = _diagnostics_metadata(state_dir=state_dir)
        (artifacts_dir / "summary.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        if include_config:
            config_path = config.config_path()
            _copy_if_exists(config_path, artifacts_dir / "config")

        if include_logs:
            log_path = daemon_manager.log_file_path(state_dir=state_dir)
            _copy_if_exists(log_path, artifacts_dir / "logs")

        if include_plugins:
            plugin_root = Path(__file__).resolve().parents[1] / "plugins"
            _copy_directory_contents([plugin_root], artifacts_dir / "plugins")

        if include_state_listing:
            state_files: list[dict[str, object]] = []
            state_listing: dict[str, object] = {
                "state_dir": str(state_path),
                "files": state_files,
            }
            for path in state_path.glob("**/*"):
                if path.is_file():
                    state_files.append({
                        "path": str(path.relative_to(state_path)),
                        "size": path.stat().st_size,
                    })
            (artifacts_dir / "state.json").write_text(json.dumps(state_listing, indent=2), encoding="utf-8")

        with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for file in artifacts_dir.rglob("*"):
                if file.is_file():
                    bundle.write(file, file.relative_to(artifacts_dir))

    return bundle_path


__all__ = ["create_diagnostics_bundle"]
