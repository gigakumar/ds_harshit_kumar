# tools/mlx_runtime.py
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import httpx  # type: ignore[import-untyped]
import numpy as np  # type: ignore[import-untyped]
from flask import Flask, jsonify, request  # type: ignore[import-untyped]

from core.audit import read_events, write_event
from core.config import (
    apply_model_profile,
    get_config,
    list_model_modes,
    list_model_profiles,
    save_config,
    set_model_mode,
)
from core.plugins import PluginManifest

try:  # pragma: no cover - optional dependency
    from huggingface_hub import InferenceClient  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - gracefully degrade when hub not available
    InferenceClient = None  # type: ignore


_BUNDLE_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def _resolve_models_root() -> Path:
    override = os.environ.get("ML_MODELS_DIR")
    if override:
        root = Path(override).expanduser().resolve()
        root.mkdir(parents=True, exist_ok=True)
        return root

    bundled = _BUNDLE_ROOT / "ml_models"
    if bundled.exists():
        return bundled

    fallback = Path.home() / ".mahi" / "models"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


MODELS_ROOT = _resolve_models_root()
_PLUGINS_DIR = Path(os.environ.get("PLUGINS_DIR", Path(__file__).resolve().parents[1] / "plugins"))

CONFIG = get_config()
MODEL_CONF: Dict[str, Any] = CONFIG.get("model", {})
MODEL_PROFILES: List[Dict[str, Any]] = list_model_profiles(CONFIG)
MODEL_BACKEND: str = str(MODEL_CONF.get("backend", "mlx"))
MODEL_MODE: str = str(MODEL_CONF.get("mode", "ml"))
MODEL_MODES: List[Dict[str, Any]] = list_model_modes(CONFIG)
DEFAULT_RUNTIME_URL = "http://127.0.0.1:9000"
RUNTIME_URL: str = str(MODEL_CONF.get("runtime_url", DEFAULT_RUNTIME_URL))
_MODEL_VERSION: str | None = None

_PERMISSIONS: Dict[str, bool] = {
    "file_access": bool(CONFIG.get("permissions", {}).get("file_access", False)),
    "network_access": bool(CONFIG.get("permissions", {}).get("network_access", False)),
    "calendar_access": bool(CONFIG.get("permissions", {}).get("calendar_access", False)),
    "mail_access": bool(CONFIG.get("permissions", {}).get("mail_access", False)),
    "browser_access": bool(CONFIG.get("permissions", {}).get("browser_access", False)),
    "shell_access": bool(CONFIG.get("permissions", {}).get("shell_access", False)),
    "automation_access": bool(CONFIG.get("permissions", {}).get("automation_access", False)),
}


def _resolve_model_path(raw: str | None) -> Optional[str]:
    if not raw:
        return None
    if raw.startswith("bundle://"):
        rel = raw.split("bundle://", 1)[1]
        return str((MODELS_ROOT / rel).resolve())
    expanded = Path(str(raw)).expanduser()
    if expanded.is_absolute():
        return str(expanded)
    return str((MODELS_ROOT / expanded).resolve())


def _ensure_mlx_weights(target_path: Optional[str]) -> None:
    if not target_path:
        return
    path = Path(target_path)
    if path.exists():
        return

    os.environ.setdefault("ML_MODELS_DIR", str(MODELS_ROOT))
    try:
        from tools.fetch_models import download_model  # pragma: no cover - import side effect only when missing
    except Exception as exc:  # pragma: no cover - optional dependency
        print(f"[runtime] Unable to import fetch_models for auto-download: {exc}", file=sys.stderr)
        return

    try:
        print(f"[runtime] Missing MLX weights at {path}, attempting download…")
        download_model(force=False)
        if path.exists():
            print(f"[runtime] MLX weights downloaded to {path}")
    except Exception as exc:  # pragma: no cover - network/gated resources
        print(f"[runtime] Auto-download failed: {exc}", file=sys.stderr)


def _fallback_embed(text: str) -> np.ndarray:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    data = np.frombuffer(digest * 8, dtype=np.uint8)[:256].astype(np.float32)
    return data / 255.0


def _fallback_generate(prompt: str, **kwargs: Any) -> str:
    goal = (prompt or "").strip()
    payload = {
        "path": "plan.txt",
        "content": goal or "No goal provided; document context for operator review.",
        "append": False,
    }
    action = {
        "name": "system.files.write",
        "payload": json.dumps(payload),
        "sensitive": False,
        "preview_required": False,
    }
    return json.dumps([action])


embed_text: Callable[[str], np.ndarray] = _fallback_embed
generate: Callable[..., str] = _fallback_generate


def _extract_json_plan(raw: str) -> str | None:
    """Extract a JSON array payload from a raw LLM response."""
    if not raw:
        return None
    candidate = raw.strip()
    if candidate.startswith("[") and candidate.endswith("]"):
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    start = candidate.find("[")
    end = candidate.rfind("]")
    if start != -1 and end != -1 and end > start:
        snippet = candidate[start : end + 1]
        try:
            json.loads(snippet)
            return snippet
        except Exception:
            return None
    return None


def _load_backend(model_conf: Dict[str, Any]) -> Tuple[Callable[[str], np.ndarray], Callable[..., str]]:
    backend = str(model_conf.get("backend", "mlx")).lower()
    embed_fn: Callable[[str], np.ndarray] = _fallback_embed
    generate_fn: Callable[..., str] = _fallback_generate

    if backend == "ollama":  # pragma: no cover - network dependency
        _ollama = model_conf.get("ollama", {})
        host = str(_ollama.get("host", "http://127.0.0.1:11434")).rstrip("/")
        model = str(_ollama.get("model", "llama3"))

        def _ollama_embed(text: str) -> np.ndarray:
            resp = httpx.post(
                f"{host}/api/embeddings",
                json={"model": model, "input": text},
                timeout=120,
            )
            resp.raise_for_status()
            payload = resp.json()
            vector = payload.get("embedding")
            if vector is None and isinstance(payload.get("data"), list):
                vector = payload["data"][0].get("embedding")
            if not vector:
                return _fallback_embed(text)
            return np.array(vector, dtype=np.float32)

        def _ollama_generate(prompt: str, **kwargs: Any) -> str:
            body = {"model": model, "prompt": prompt, "stream": False}
            if kwargs:
                body["options"] = kwargs
            resp = httpx.post(f"{host}/api/generate", json=body, timeout=240)
            resp.raise_for_status()
            data = resp.json()
            return str(data.get("response", "")).strip()

        embed_fn = _ollama_embed
        generate_fn = _ollama_generate

    elif backend == "openai":  # pragma: no cover - network dependency
        _openai_conf = model_conf.get("openai", {})
        api_key = str(_openai_conf.get("api_key") or os.environ.get("OPENAI_API_KEY", "")).strip()
        chat_model = str(_openai_conf.get("chat_model", "gpt-4o-mini"))
        embed_model = str(_openai_conf.get("embedding_model", "text-embedding-3-small"))

        if api_key:

            def _openai_embed(text: str) -> np.ndarray:
                resp = httpx.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={"model": embed_model, "input": text},
                    timeout=120,
                )
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data", [])
                if data:
                    vector = data[0].get("embedding", [])
                    return np.array(vector, dtype=np.float32)
                return _fallback_embed(text)

            def _openai_generate(prompt: str, **kwargs: Any) -> str:
                params = {
                    "model": chat_model,
                    "messages": [
                        {"role": "system", "content": "You are a concise automation planner."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": float(kwargs.get("temperature", 0.2)),
                    "max_tokens": int(kwargs.get("max_tokens", 512)),
                }
                resp = httpx.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=params,
                    timeout=240,
                )
                resp.raise_for_status()
                payload = resp.json()
                choices = payload.get("choices", [])
                if choices:
                    return str(choices[0].get("message", {}).get("content", "")).strip()
                return _fallback_generate(prompt, **kwargs)

            embed_fn = _openai_embed
            generate_fn = _openai_generate

    elif backend in {"hf", "huggingface", "huggingface_hub"}:
        hf_conf = model_conf.get("huggingface", {})
        model_id = str(
            hf_conf.get(
                "model_id",
                os.environ.get("HF_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.2"),
            )
        )
        token = hf_conf.get("token") or os.environ.get("HUGGINGFACEHUB_API_TOKEN")
        embed_model = str(
            hf_conf.get("embedding_model", os.environ.get("HF_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"))
        )

        if InferenceClient is not None:
            try:
                client = InferenceClient(model=model_id, token=token)
            except Exception:
                client = None  # type: ignore
        else:
            client = None  # type: ignore

        def _hf_embed(text: str) -> np.ndarray:
            if client is None:
                return _fallback_embed(text)
            try:
                result = client.feature_extraction(text, model=embed_model)
                vector = np.array(result, dtype=np.float32)
                if vector.ndim == 2:
                    vector = vector.mean(axis=0)
                norm = np.linalg.norm(vector) or 1.0
                return (vector / norm).astype(np.float32)
            except Exception:
                return _fallback_embed(text)

        def _hf_generate(prompt: str, **kwargs: Any) -> str:
            if client is None:
                return _fallback_generate(prompt, **kwargs)
            temperature = float(kwargs.get("temperature", 0.2))
            max_tokens = int(kwargs.get("max_tokens", 512))
            top_p = float(kwargs.get("top_p", 0.95))
            system_prompt = (
                "You are an automation planner. Respond with JSON array of actions using keys "
                "name, payload (JSON string), sensitive, preview_required."
            )
            composed_prompt = f"{system_prompt}\n\nGoal: {prompt}\nResponse:"
            try:
                response = client.text_generation(
                    composed_prompt,
                    max_new_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p,
                )
            except Exception:
                return _fallback_generate(prompt, **kwargs)

            if isinstance(response, str):
                raw_text = response
            else:  # huggingface_hub may return a dict-like object
                raw_text = getattr(response, "generated_text", "")
            extracted = _extract_json_plan(raw_text)
            if extracted:
                return extracted
            return _fallback_generate(prompt, **kwargs)

        embed_fn = _hf_embed
        generate_fn = _hf_generate

    else:  # MLX backend
        try:  # pragma: no cover - optional dependency
            from mlx_lm import load_model  # type: ignore[import]

            mlx_conf = model_conf.get("mlx", {})
            target_path = _resolve_model_path(mlx_conf.get("model_path"))
            model_name = str(mlx_conf.get("model_name", "mlx-community/mistral-7b-instruct-q4_0"))
            _ensure_mlx_weights(target_path)
            planner_target: Path | None
            env_target = os.environ.get("PLANNER_MODEL_PATH")
            if env_target:
                planner_target = Path(env_target)
            elif target_path:
                planner_target = Path(target_path)
            else:
                planner_target = None

            if planner_target and planner_target.exists():
                model = load_model(str(planner_target), device="metal")
            else:
                model = load_model(os.environ.get("PLANNER_MODEL_NAME", model_name), device="metal")

            def _model_embed(text: str) -> np.ndarray:
                return np.array(model.embed(text), dtype=np.float32)

            def _model_generate(prompt: str, **kwargs: Any) -> str:
                return model.generate(prompt, **kwargs)

            embed_fn = _model_embed
            generate_fn = _model_generate
        except Exception:
            pass

    return embed_fn, generate_fn


def _ensure_backend() -> None:
    global CONFIG, MODEL_CONF, MODEL_BACKEND, MODEL_MODE, MODEL_PROFILES, MODEL_MODES, RUNTIME_URL, embed_text, generate, _MODEL_VERSION
    config = get_config()
    model_conf = config.get("model", {})
    version = json.dumps(model_conf, sort_keys=True)
    if version == _MODEL_VERSION:
        return

    embed_fn, generate_fn = _load_backend(model_conf)
    embed_text = embed_fn
    generate = generate_fn
    CONFIG = config
    MODEL_CONF = model_conf
    MODEL_BACKEND = str(model_conf.get("backend", "mlx"))
    MODEL_MODE = str(model_conf.get("mode", "ml"))
    RUNTIME_URL = str(model_conf.get("runtime_url", DEFAULT_RUNTIME_URL))
    MODEL_PROFILES = list_model_profiles(config)
    MODEL_MODES = list_model_modes(config)
    _MODEL_VERSION = version


_ensure_backend()


app = Flask("mlx_runtime")


@app.before_request
def _refresh_backend_state() -> None:
    _ensure_backend()

_DOCUMENTS: Dict[str, Dict[str, Any]] = {}
_VECTORS: Dict[str, np.ndarray] = {}


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _doc_preview(text: str) -> str:
    return text[:200]


@app.route("/health", methods=["GET"])
def health() -> Any:
    _ensure_backend()
    plugins_enabled = (_PLUGINS_DIR / "plugin-manifest.yaml").exists()
    return jsonify(
        {
            "status": "ok",
            "documents": len(_DOCUMENTS),
            "backend": MODEL_BACKEND,
            "profile": MODEL_CONF.get("profile"),
            "mode": MODEL_CONF.get("mode", "ml"),
            "plugins": plugins_enabled,
        }
    )


@app.route("/embed", methods=["POST"])
def embed() -> Any:
    payload = request.get_json(silent=True) or {}
    texts: Iterable[str] = payload.get("texts", [])
    vectors = [embed_text(text).astype(float).tolist() for text in texts]
    return jsonify({"vectors": vectors})


@app.route("/predict", methods=["POST"])
def predict() -> Any:
    payload = request.get_json(silent=True) or {}
    prompt = payload.get("prompt", "")
    params = payload.get("params", {}) or {}
    return jsonify({"text": generate(prompt, **params)})


@app.route("/index", methods=["POST"])
def index_document() -> Any:
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("text", "")).strip()
    if not text:
        return jsonify({"error": "text is required"}), 400
    source = (payload.get("source") or "api").strip() or "api"
    doc_id = str(uuid.uuid4())
    ts = int(time.time())
    vector = embed_text(text)
    _DOCUMENTS[doc_id] = {"id": doc_id, "source": source, "ts": ts, "text": text}
    _VECTORS[doc_id] = vector
    write_event({"type": "document_indexed", "id": doc_id, "source": source})
    return jsonify({"id": doc_id, "source": source, "ts": ts, "preview": _doc_preview(text)})


@app.route("/query", methods=["POST"])
def semantic_query() -> Any:
    payload = request.get_json(silent=True) or {}
    query = str(payload.get("query", "")).strip()
    limit = int(payload.get("limit", 5) or 5)
    if not query:
        return jsonify({"hits": []})
    q_vec = embed_text(query)
    scored: List[Dict[str, Any]] = []
    for doc_id, vector in _VECTORS.items():
        score = _cosine(q_vec, vector)
        doc = _DOCUMENTS[doc_id]
        scored.append({"doc_id": doc_id, "score": score, "preview": _doc_preview(doc["text"])})
    scored.sort(key=lambda item: item["score"], reverse=True)
    return jsonify({"hits": scored[: limit if limit > 0 else 5]})


@app.route("/plan", methods=["POST"])
def plan() -> Any:
    payload = request.get_json(silent=True) or {}
    goal = payload.get("goal", "")
    params = payload.get("params", {}) or {}
    try:
        actions = json.loads(generate(f"Plan steps for: {goal}", **params))
        if isinstance(actions, list):
            return jsonify({"actions": actions})
    except Exception:
        pass
    return jsonify({
        "actions": [
            {"name": "research", "payload": json.dumps({"goal": goal}), "sensitive": False, "preview_required": False},
            {"name": "summarize", "payload": json.dumps({"goal": goal}), "sensitive": False, "preview_required": False},
        ]
    })


@app.route("/documents", methods=["GET"])
def list_documents() -> Any:
    docs = [
        {"id": doc_id, "source": doc["source"], "ts": doc["ts"], "preview": _doc_preview(doc["text"])}
        for doc_id, doc in _DOCUMENTS.items()
    ]
    docs.sort(key=lambda d: d["ts"], reverse=True)
    return jsonify({"documents": docs})


@app.route("/documents/<doc_id>", methods=["GET"])
def document_detail(doc_id: str) -> Any:
    doc = _DOCUMENTS.get(doc_id)
    if not doc:
        return jsonify({"error": "not_found"}), 404
    return jsonify(doc)


@app.route("/audit", methods=["GET", "POST"])
def audit() -> Any:
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        write_event(payload)
        return jsonify({"status": "ok"}), 201
    events = list(read_events())
    return jsonify({"events": events})


@app.route("/permissions", methods=["GET", "POST"])
def permissions() -> Any:
    global CONFIG, _PERMISSIONS
    if request.method == "POST":
        payload = request.get_json(silent=True) or {}
        updated = dict(_PERMISSIONS)
        for key in list(updated.keys()):
            if key in payload:
                updated[key] = bool(payload[key])
        _PERMISSIONS = updated
        CONFIG = get_config()
        CONFIG.setdefault("permissions", {}).update(_PERMISSIONS)
        save_config(CONFIG)
        write_event({"type": "permissions_update", "permissions": _PERMISSIONS})
        return jsonify({"permissions": _PERMISSIONS})
    return jsonify({"permissions": _PERMISSIONS})


@app.route("/model", methods=["GET", "POST"])
def model_config() -> Any:
    _ensure_backend()
    if request.method == "GET":
        profiles = [dict(profile) for profile in MODEL_PROFILES if isinstance(profile, dict)]
        active = MODEL_CONF.get("profile")
        for profile in profiles:
            profile["selected"] = profile.get("id") == active
        modes = [dict(mode) for mode in MODEL_MODES if isinstance(mode, dict)]
        active_mode = MODEL_CONF.get("mode", "ml")
        for mode in modes:
            mode["selected"] = mode.get("id") == active_mode
        return jsonify(
            {
                "profile": active,
                "backend": MODEL_CONF.get("backend"),
                "runtime_url": MODEL_CONF.get("runtime_url", RUNTIME_URL),
                "mode": active_mode,
                "profiles": profiles,
                "modes": modes,
            }
        )

    payload = request.get_json(silent=True) or {}
    profile_id = payload.get("profile") or payload.get("profile_id")
    mode_id = payload.get("mode") or payload.get("mode_id")
    if not profile_id and not mode_id:
        return jsonify({"error": "profile_or_mode_required"}), 400

    overrides: Dict[str, Any] = {}
    settings = payload.get("settings")
    if isinstance(settings, dict):
        overrides.update(settings)
    runtime_url = payload.get("runtime_url")
    backend = payload.get("backend")
    if runtime_url:
        overrides["runtime_url"] = runtime_url
    if backend:
        overrides["backend"] = backend

    if profile_id:
        try:
            apply_model_profile(str(profile_id), overrides or None)
        except KeyError:
            return jsonify({"error": "unknown_profile", "profile": profile_id}), 404

    if mode_id:
        try:
            set_model_mode(str(mode_id))
        except KeyError:
            return jsonify({"error": "unknown_mode", "mode": mode_id}), 404

    _ensure_backend()
    profiles = [dict(profile) for profile in MODEL_PROFILES if isinstance(profile, dict)]
    active = MODEL_CONF.get("profile")
    for profile in profiles:
        profile["selected"] = profile.get("id") == active
    modes = [dict(mode) for mode in MODEL_MODES if isinstance(mode, dict)]
    active_mode = MODEL_CONF.get("mode", "ml")
    for mode in modes:
        mode["selected"] = mode.get("id") == active_mode
    if profile_id:
        write_event({"type": "model_profile_update", "profile": active, "backend": MODEL_CONF.get("backend")})
    if mode_id:
        write_event({"type": "model_mode_update", "mode": active_mode})
    return jsonify(
        {
            "profile": active,
            "backend": MODEL_CONF.get("backend"),
            "runtime_url": MODEL_CONF.get("runtime_url", RUNTIME_URL),
            "mode": active_mode,
            "profiles": profiles,
            "modes": modes,
        }
    )


@app.route("/plugins", methods=["GET"])
def plugins() -> Any:
    manifest_path = _PLUGINS_DIR / "plugin-manifest.yaml"
    if not manifest_path.exists():
        return jsonify({"plugins": []})
    manifest = PluginManifest.load(str(manifest_path))
    return jsonify({"plugins": [manifest.__dict__]})


if __name__ == "__main__":  # pragma: no cover
    app.run(host="127.0.0.1", port=9000)
