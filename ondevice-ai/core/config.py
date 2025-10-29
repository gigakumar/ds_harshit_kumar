"""Configuration helpers for the automation daemon."""
from __future__ import annotations

import copy
import json
import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterator, Optional, Sequence, Tuple

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
        "network_access": False,
        "calendar_access": False,
        "mail_access": False,
        "browser_access": False,
        "shell_access": False,
        "automation_access": False,
    },
    "auth": {
        "bootstrap_token": "",
        "token_ttl_seconds": 3600,
        "rate_limit_per_minute": 120,
        "enforce_tls": True,
        "token_store": {
            "backend": "keyring",
            "keyring_service": "mahi-automation",
            "file_path": "state/tokens.enc",
        },
    },
    "telemetry": {
        "enabled": False,
        "retention_days": 30,
        "remote_upload": {
            "enabled": False,
            "endpoint": "",
        },
    },
    "registry": {
        "database": "state/registry.db",
        "manifests": [],
        "auto_preload": False,
    },
    "templates": {
        "paths": ["templates"],
    },
    "sandbox": {
        "working_dir": "./sandbox",
        "cpu_time_seconds": 10,
        "wall_time_seconds": 15.0,
        "memory_bytes": 1_073_741_824,
        "allow_subprocesses": False,
        "allow_network": False,
        "max_open_files": 512,
        "max_processes": 128,
        "max_output_bytes": 268_435_456,
        "idle_priority": True,
        "nice_increment": 10,
        "collect_usage": True,
    },
    "dashboard": {
        "quick_goals": [
            {
                "id": "daily-briefing",
                "label": "Daily Briefing",
                "description": "Plan a review of today's calendar, mail, and top headlines.",
                "goal": (
                    "Assemble a daily briefing that covers upcoming calendar items, priority emails, and the biggest news stories. "
                    "Summarize actionable next steps for the day."
                ),
                "category": "Briefings",
                "mode": "auto",
                "fields": [],
            },
            {
                "id": "research-topic",
                "label": "Research Topic",
                "description": "Compile a concise research memo for a topic you provide.",
                "goal": (
                    "Research the topic '{{topic}}' across trusted sources. Produce a 5-bullet briefing including fast facts, "
                    "open questions, and suggested follow-ups."
                ),
                "category": "Research",
                "mode": "plan",
                "fields": [
                    {
                        "key": "topic",
                        "label": "Topic",
                        "placeholder": "e.g. Apple Vision Pro updates",
                    }
                ],
            },
            {
                "id": "draft-email",
                "label": "Draft Email Reply",
                "description": "Generate a polite reply for the pasted email thread context.",
                "goal": (
                    "Given the email thread provided below, craft a polite and efficient reply that addresses all questions, "
                    "sets clear next steps, and highlights any outstanding decisions."
                ),
                "category": "Communication",
                "mode": "plan",
                "fields": [
                    {
                        "key": "thread",
                        "label": "Email Thread",
                        "placeholder": "Paste the relevant email conversation here",
                        "multiline": True,
                    }
                ],
            },
            {
                "id": "inbox-triage",
                "label": "Inbox Triage",
                "description": "Sort unread emails by urgency and suggest quick responses.",
                "goal": (
                    "Review the mailbox '{{mailbox}}' and group unread messages by urgency and topic. Summarize the top "
                    "items with suggested next steps or reply drafts. Flag anything requiring immediate attention."
                ),
                "category": "Productivity",
                "mode": "plan",
                "fields": [
                    {
                        "key": "mailbox",
                        "label": "Mailbox",
                        "placeholder": "e.g. Work/Inbox",
                    }
                ],
            },
            {
                "id": "task-scheduler",
                "label": "Task Scheduler",
                "description": "Turn a task list into a schedule with deadlines and reminders.",
                "goal": (
                    "Using the task list below, create a prioritized execution plan for the coming week. Assign deadlines, "
                    "owners if provided, and recommended reminders or follow-ups for each task."
                ),
                "category": "Planning",
                "mode": "plan",
                "fields": [
                    {
                        "key": "tasks",
                        "label": "Tasks",
                        "placeholder": "List tasks with optional owners or due dates",
                        "multiline": True,
                    }
                ],
            },
            {
                "id": "cleanup-downloads",
                "label": "Clean Downloads Folder",
                "description": "Audit the Downloads folder and archive or delete clutter safely.",
                "goal": (
                    "Inspect the folder at '{{path}}'. Identify temporary, duplicate, or large files older than {{days_old}} "
                    "days. Prepare a cleanup report and optional shell commands to archive or delete safely."
                ),
                "category": "System",
                "mode": "plan",
                "fields": [
                    {
                        "key": "path",
                        "label": "Folder Path",
                        "placeholder": "~/Downloads",
                    },
                    {
                        "key": "days_old",
                        "label": "Older Than (days)",
                        "placeholder": "14",
                    }
                ],
            },
        ],
    },
    "runtime_pool": {
        "enabled": False,
        "executable": "automation_daemon.py",
        "min_runtimes": 0,
        "max_runtimes": 1,
        "base_port": 9600,
        "heartbeat_seconds": 5.0,
        "restart_backoff": 3.0,
    },
    "supervisor": {
        "enabled": True,
        "max_restarts": 5,
        "window_seconds": 60.0,
        "backoff_seconds": 2.0,
        "max_backoff_seconds": 30.0,
        "graceful_shutdown_seconds": 10.0,
        "health_enabled": True,
        "health_host": "127.0.0.1",
        "health_port": 0,
        "health_path": "/healthz",
    },
}


_OVERRIDE_ENV_PREFIX = "MAHI_CFG__"
_SECRET_ENV_PREFIX = "MAHI_SECRET__"
_OVERRIDE_JSON_ENV = "MAHI_CONFIG_OVERRIDES"
_SECRET_JSON_ENV = "MAHI_SECRET_OVERRIDES"

_SECRET_KEY_HINTS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "auth",
)

_SECRET_PATHS: set[Tuple[str, ...]] = set()


def _default_profiles() -> list[Dict[str, Any]]:
    profiles = _DEFAULT_CONFIG.get("model", {}).get("profiles", [])
    if isinstance(profiles, list):
        return [copy.deepcopy(profile) for profile in profiles if isinstance(profile, dict)]
    return []


def _default_modes() -> list[Dict[str, Any]]:
    modes = _DEFAULT_CONFIG.get("model", {}).get("modes", [])
    if isinstance(modes, list):
        return [copy.deepcopy(mode) for mode in modes if isinstance(mode, dict)]
    return []


def _config_path() -> Path:
    env = os.environ.get("MAHI_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[1] / "config" / "automation.yaml"


def config_path() -> Path:
    """Return the resolved configuration file path without loading."""
    return _config_path()


def _merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            base[key] = _merge(dict(base[key]), value)  # type: ignore[arg-type]
        else:
            base[key] = value
    return base


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(hint in lowered for hint in _SECRET_KEY_HINTS)


def _normalize_env_path(raw: str) -> Sequence[str]:
    parts = [part for part in raw.split("__") if part]
    normalized: list[str] = []
    for part in parts:
        normalized.append(part.strip().lower().replace("-", "_"))
    return normalized


def _coerce_override_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped == "":
        return ""
    try:
        parsed = yaml.safe_load(stripped)
    except Exception:
        return value
    return parsed


def _assign_path(target: Dict[str, Any], path: Sequence[str], value: Any) -> None:
    if not path:
        return
    cursor: Dict[str, Any] = target
    for key in path[:-1]:
        key = key.strip()
        existing = cursor.get(key)
        if not isinstance(existing, dict):
            existing = {}
            cursor[key] = existing
        cursor = existing
    cursor[path[-1].strip()] = value


def _collect_leaf_paths(data: Any, prefix: Tuple[str, ...] | None = None) -> Iterator[Tuple[str, ...]]:
    prefix = prefix or tuple()
    if isinstance(data, dict):
        for key, value in data.items():
            key_str = str(key)
            yield from _collect_leaf_paths(value, prefix + (key_str,))
    else:
        yield prefix


def _collect_secret_hint_paths(data: Any, prefix: Tuple[str, ...] | None = None) -> set[Tuple[str, ...]]:
    prefix = prefix or tuple()
    found: set[Tuple[str, ...]] = set()
    if isinstance(data, dict):
        for key, value in data.items():
            key_str = str(key)
            new_prefix = prefix + (key_str,)
            if isinstance(value, dict):
                found.update(_collect_secret_hint_paths(value, new_prefix))
            elif _is_secret_key(key_str):
                found.add(new_prefix)
    return found


def _decode_mapping(raw: str) -> Dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = yaml.safe_load(raw)
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def _load_runtime_overrides() -> tuple[Dict[str, Any], set[Tuple[str, ...]]]:
    overrides: Dict[str, Any] = {}
    secret_paths: set[Tuple[str, ...]] = set()

    for key, value in os.environ.items():
        if key.startswith(_OVERRIDE_ENV_PREFIX):
            path = _normalize_env_path(key[len(_OVERRIDE_ENV_PREFIX):])
            if path:
                _assign_path(overrides, path, _coerce_override_value(value))
                if _is_secret_key(path[-1]):
                    secret_paths.add(tuple(path))
        elif key.startswith(_SECRET_ENV_PREFIX):
            path = _normalize_env_path(key[len(_SECRET_ENV_PREFIX):])
            if path:
                _assign_path(overrides, path, _coerce_override_value(value))
                secret_paths.add(tuple(path))

    json_payload = os.environ.get(_OVERRIDE_JSON_ENV)
    if json_payload:
        mapping = _decode_mapping(json_payload)
        if mapping:
            overrides = _merge(overrides, mapping)
            secret_paths.update(_collect_secret_hint_paths(mapping))

    secret_json = os.environ.get(_SECRET_JSON_ENV)
    if secret_json:
        mapping = _decode_mapping(secret_json)
        if mapping:
            overrides = _merge(overrides, mapping)
            secret_paths.update(_collect_leaf_paths(mapping))

    return overrides, secret_paths


def _delete_path(target: Dict[str, Any], path: Tuple[str, ...]) -> None:
    if not path:
        return
    cursor: Any = target
    for key in path[:-1]:
        if not isinstance(cursor, dict):
            return
        cursor = cursor.get(key)
    if isinstance(cursor, dict):
        cursor.pop(path[-1], None)


def parse_override_value(raw: str) -> Any:
    """Parse a configuration override value using the same coercion as runtime overrides."""
    return _coerce_override_value(raw)


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


def get_config(*, include_runtime_overrides: bool = True) -> Dict[str, Any]:
    """Return a copy of the merged configuration."""
    path = str(_config_path())
    config = copy.deepcopy(_load_config(path))
    _SECRET_PATHS.clear()
    if include_runtime_overrides:
        overrides, secret_paths = _load_runtime_overrides()
        if overrides:
            config = _merge(config, overrides)
        if secret_paths:
            _SECRET_PATHS.update(secret_paths)
    return config


def save_config(config: Dict[str, Any]) -> None:
    """Persist configuration to disk and refresh the cache."""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    to_write = copy.deepcopy(config)
    for secret_path in _SECRET_PATHS:
        _delete_path(to_write, secret_path)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(to_write, handle, sort_keys=False)
    _load_config.cache_clear()  # type: ignore[attr-defined]


def list_model_profiles(config: Optional[Dict[str, Any]] = None) -> list[Dict[str, Any]]:
    """Return model profile descriptors for the UI."""
    cfg = config or get_config()
    model_cfg = cfg.get("model", {})
    candidates = model_cfg.get("profiles")
    normalized: list[Dict[str, Any]] = []
    seen: set[str] = set()
    has_candidates = False

    if isinstance(candidates, list) and candidates:
        has_candidates = True
        for profile in candidates:
            if isinstance(profile, dict):
                identifier = str(profile.get("id", ""))
                seen.add(identifier)
                normalized.append(copy.deepcopy(profile))

    if not has_candidates:
        for fallback in _default_profiles():
            identifier = str(fallback.get("id", ""))
            if identifier and identifier not in seen:
                normalized.append(fallback)
                seen.add(identifier)

    return normalized


def list_model_modes(config: Optional[Dict[str, Any]] = None) -> list[Dict[str, Any]]:
    """Return available model execution modes."""
    cfg = config or get_config()
    model_cfg = cfg.get("model", {})
    candidates = model_cfg.get("modes")
    normalized: list[Dict[str, Any]] = []
    seen: set[str] = set()
    has_candidates = False

    if isinstance(candidates, list) and candidates:
        has_candidates = True
        for mode in candidates:
            if isinstance(mode, dict):
                identifier = str(mode.get("id", ""))
                seen.add(identifier)
                normalized.append(copy.deepcopy(mode))

    if not has_candidates:
        for fallback in _default_modes():
            identifier = str(fallback.get("id", ""))
            if identifier and identifier not in seen:
                normalized.append(fallback)
                seen.add(identifier)

    return normalized


def set_model_mode(mode_id: str, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Persist the active model execution mode."""
    config = config_override or get_config()
    model_cfg = config.setdefault("model", {})
    available_modes = list_model_modes(config)
    target = next((mode for mode in available_modes if isinstance(mode, dict) and mode.get("id") == mode_id), None)
    if not target:
        raise KeyError(f"Unknown model mode: {mode_id}")
    stored_modes = model_cfg.setdefault("modes", [])
    if isinstance(stored_modes, list) and not any(isinstance(mode, dict) and mode.get("id") == mode_id for mode in stored_modes):
        stored_modes.append(copy.deepcopy(target))
    model_cfg["mode"] = mode_id
    save_config(config)
    return config


def apply_model_profile(profile_id: str, overrides: Optional[Dict[str, Any]] = None, *, config_override: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Update the active model profile and persist the configuration."""
    config = config_override or get_config()
    model_cfg = config.setdefault("model", {})
    profiles = list_model_profiles(config)
    target = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None)
    if not target:
        raise KeyError(f"Unknown model profile: {profile_id}")

    backend = target.get("backend") or model_cfg.get("backend", "mlx")
    model_cfg["profile"] = profile_id
    model_cfg["backend"] = backend
    stored_profiles = model_cfg.setdefault("profiles", [])
    if isinstance(stored_profiles, list) and not any(isinstance(profile, dict) and profile.get("id") == profile_id for profile in stored_profiles):
        stored_profiles.append(copy.deepcopy(target))
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


def list_quick_goals(config: Optional[Dict[str, Any]] = None) -> list[Dict[str, Any]]:
    cfg = config or get_config()
    dashboard = cfg.get("dashboard", {})
    goals = dashboard.get("quick_goals", [])
    if isinstance(goals, list):
        return [copy.deepcopy(goal) for goal in goals if isinstance(goal, dict)]
    return []


def save_quick_goal(goal: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(goal, dict):
        raise TypeError("Goal must be a dictionary")
    config = get_config()
    dashboard = config.setdefault("dashboard", {})
    goals = dashboard.setdefault("quick_goals", [])
    if not isinstance(goals, list):
        dashboard["quick_goals"] = goals = []

    goal_id = str(goal.get("id") or uuid.uuid4())
    normalized = dict(goal)
    normalized["id"] = goal_id
    normalized.setdefault("label", "Untitled Goal")
    normalized.setdefault("goal", "")
    normalized.setdefault("category", "Custom")
    normalized.setdefault("mode", "plan")
    fields = normalized.get("fields", [])
    if isinstance(fields, list):
        normalized["fields"] = [field for field in fields if isinstance(field, dict)]
    else:
        normalized["fields"] = []

    for index, existing in enumerate(list(goals)):
        if isinstance(existing, dict) and existing.get("id") == goal_id:
            goals[index] = normalized
            break
    else:
        goals.append(normalized)

    save_config(config)
    return config


def delete_quick_goal(goal_id: str) -> Dict[str, Any]:
    if not goal_id:
        raise ValueError("Goal id required")
    config = get_config()
    dashboard = config.setdefault("dashboard", {})
    goals = dashboard.setdefault("quick_goals", [])
    if isinstance(goals, list):
        dashboard["quick_goals"] = [goal for goal in goals if not (isinstance(goal, dict) and goal.get("id") == goal_id)]
    else:
        dashboard["quick_goals"] = []
    save_config(config)
    return config


__all__ = [
    "get_config",
    "save_config",
    "list_model_profiles",
    "list_model_modes",
    "apply_model_profile",
    "set_model_mode",
    "list_quick_goals",
    "save_quick_goal",
    "delete_quick_goal",
]
