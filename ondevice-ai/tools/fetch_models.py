#!/usr/bin/env python
"""Download and stage bundled MLX models for offline packaging."""
from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path
from typing import Iterable

try:
    from huggingface_hub import snapshot_download  # type: ignore[import-untyped]
except ImportError as exc:  # pragma: no cover - guidance message
    raise SystemExit(
        "huggingface-hub is required. Install with `pip install huggingface_hub`."
    ) from exc

REPO_ID = "mlx-community/tinyllama-1.1b-chat-q4f16_1"
ALLOW_PATTERNS: Iterable[str] = (
    "*.json",
    "*.safetensors",
    "tokenizer.*",
    "*.model",
    "*.txt",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SUBDIR = "tinyllama-1.1b-chat-q4f16_1"


def _resolve_destination() -> Path:
    base = os.environ.get("ML_MODELS_DIR")
    if base:
        return Path(base).expanduser().resolve() / SUBDIR
    return PROJECT_ROOT / "ml_models" / SUBDIR


def download_model(force: bool = False) -> Path:
    """Download the TinyLlama snapshot and copy it into ml_models."""
    dest_dir = _resolve_destination()
    if dest_dir.exists() and not force:
        print(f"Model already present at {dest_dir}. Skipping download.")
        return dest_dir

    print(f"Fetching {REPO_ID} from Hugging Face…")
    snapshot_path = Path(
        snapshot_download(
            repo_id=REPO_ID,
            allow_patterns=list(ALLOW_PATTERNS),
            cache_dir=str(PROJECT_ROOT / ".hf-cache"),
            local_dir_use_symlinks=False,
        )
    )

    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    shutil.copytree(snapshot_path, dest_dir)
    manifest = {
        "repo": REPO_ID,
        "source": "huggingface",
        "files": sorted(p.name for p in dest_dir.iterdir()),
    }
    (dest_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Model copied to {dest_dir}")
    return dest_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch TinyLlama weights for packaging.")
    parser.add_argument("--force", action="store_true", help="Re-download even if the folder exists.")
    args = parser.parse_args()
    download_model(force=args.force)


if __name__ == "__main__":  
    main()
