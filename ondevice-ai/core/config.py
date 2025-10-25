"""Configuration helpers for the automation daemon."""
from __future__ import annotations

import copy
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml  # type: ignore[import-untyped]

_DEFAULT_CONFIG: Dict[str, Any] = {
    "model": {
        "profile": "mlx_tinyllama",
        "backend": "mlx",
        "mode": "ml",
        "runtime_url": "http://127.0.0.1:9000",
        "modes": [
            {
                "id": "ml",
                "label": "Machine Learning",
                "description": "Use the configured language model runtime for embeddings and planning.",
                "capabilities": ["planning", "embeddings", "semantic-search"],
            },
            {
                "id": "rules",
                "label": "Rules Engine",
                "description": "Disable ML calls and fall back to deterministic rule-based routines.",
                "capabilities": ["deterministic", "offline", "fast-start"],
            },
        ],
        "profiles": [
            {
                "id": "mlx_tinyllama",
                "label": "On-device TinyLlama",
                "backend": "mlx",
                "description": "Ship-ready TinyLlama 1.1B chat weights bundled with the app for fully offline planning.",
                "capabilities": ["offline", "fast-planning", "no-network"],
                "settings": {
                    "mlx": {
                        "model_path": "bundle://tinyllama-1.1b-chat-q4f16_1",
                        "model_name": "mlx-community/tinyllama-1.1b-chat-q4f16_1",
                    }
                },
            },
            {
                "id": "ollama_llama3",
                "label": "Ollama Llama 3",
                "backend": "ollama",
                "description": "Leverage an Ollama-managed Llama 3 model running elsewhere on your LAN.",
                "capabilities": ["context-resident", "multi-user"],
                "settings": {
                    "ollama": {
                        "host": "http://127.0.0.1:11434",
                        "model": "llama3",
                    }
                },
            },
            {
                "id": "openai_gpt4o",
                "label": "OpenAI GPT-4o mini",
                "backend": "openai",
                "description": "Use OpenAI's GPT-4o-mini APIs for higher quality planning with network access.",
                "capabilities": ["cloud", "high-quality"],
                "settings": {
                    "openai": {
                        "chat_model": "gpt-4o-mini",
                        "embedding_model": "text-embedding-3-small",
                    }
                },
                "requires": {
                    "environment": ["OPENAI_API_KEY"],
                },
            },
        ],
        "mlx": {
            "model_path": "bundle://tinyllama-1.1b-chat-q4f16_1",
            "model_name": "mlx-community/tinyllama-1.1b-chat-q4f16_1",
        },
        "ollama": {
            "host": "http://127.0.0.1:11434",
            "model": "llama3",
        },
        "openai": {
            "api_key": "",
            "chat_model": "gpt-4o-mini",
            "embedding_model": "text-embedding-3-small",
        },
    },
    "permissions": {
        "file_access": False,
        "calendar_access": False,
        "mail_access": False,
    },
}


def _config_path() -> Path:
    env = os.environ.get("MAHI_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "config" / "automation.yaml"


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge(dict(base[key]), value)  # type: ignore[arg-type]
        else:
            base[key] = value
    return base


@lru_cache(maxsize=4)
def _load_config(resolved_path: str) -> Dict[str, Any]:
    base = copy.deepcopy(_DEFAULT_CONFIG)
    path = Path(resolved_path)
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
        if isinstance(data, dict):
            base = _merge(base, data)
    return base


def get_config() -> Dict[str, Any]:
    """Return a copy of the merged configuration."""
    path = str(_config_path())
    return copy.deepcopy(_load_config(path))


def save_config(config: Dict[str, Any]) -> None:
    """Persist configuration to disk and refresh the cache."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False)
    _load_config.cache_clear()  # type: ignore[attr-defined]


def list_model_profiles(config: Optional[Dict[str, Any]] = None) -> list[Dict[str, Any]]:
    """Return model profile descriptors for the UI."""
    cfg = config or get_config()
    model_cfg = cfg.get("model", {})
    profiles = model_cfg.get("profiles", [])
    if isinstance(profiles, list):
        return [copy.deepcopy(p) for p in profiles if isinstance(p, dict)]
    return []


def list_model_modes(config: Optional[Dict[str, Any]] = None) -> list[Dict[str, Any]]:
    """Return available model execution modes."""
    cfg = config or get_config()
    model_cfg = cfg.get("model", {})
    modes = model_cfg.get("modes", [])
    if isinstance(modes, list):
        return [copy.deepcopy(mode) for mode in modes if isinstance(mode, dict)]
    return []


def set_model_mode(mode_id: str, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Persist the active model execution mode."""
    config = config_override or get_config()
    model_cfg = config.setdefault("model", {})
    modes = model_cfg.get("modes", []) or []
    if not any(isinstance(mode, dict) and mode.get("id") == mode_id for mode in modes):
        raise KeyError(f"Unknown model mode: {mode_id}")
    model_cfg["mode"] = mode_id
    save_config(config)
    return config


def apply_model_profile(profile_id: str, overrides: Optional[Dict[str, Any]] = None, *, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Update the active model profile and persist the configuration."""
    config = config_override or get_config()
    model_cfg = config.setdefault("model", {})
    profiles = model_cfg.get("profiles", []) or []
    target = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None)
    if not target:
        raise KeyError(f"Unknown model profile: {profile_id}")

    backend = target.get("backend") or model_cfg.get("backend", "mlx")
    model_cfg["profile"] = profile_id
    model_cfg["backend"] = backend
    model_cfg.setdefault("mode", "ml")

    for key, value in (target.get("settings") or {}).items():
        if isinstance(value, dict) and isinstance(model_cfg.get(key), dict):
            model_cfg[key] = _merge(dict(model_cfg[key]), value)  # type: ignore[arg-type]
        else:
            model_cfg[key] = value

    for key, value in (overrides or {}).items():
        if key in {"profile", "id"}:
            continue
        if isinstance(value, dict) and isinstance(model_cfg.get(key), dict):
            model_cfg[key] = _merge(dict(model_cfg[key]), value)  # type: ignore[arg-type]
        else:
            model_cfg[key] = value

    save_config(config)
    return config


__all__ = [
    "get_config",
    "save_config",
    "list_model_profiles",
    "list_model_modes",
    "apply_model_profile",
    "set_model_mode",
]
