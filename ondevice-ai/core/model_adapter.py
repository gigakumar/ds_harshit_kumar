# core/model_adapter.py
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Iterable, Sequence

import httpx  # type: ignore[import-untyped]

from core.config import get_config


class _RuleBasedAdapter:
    """Deterministic planner used when ML mode is disabled."""

    _VECTOR_SIZE = 96

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vectors.append(self._vectorize(text))
        return vectors

    async def predict(self, goal: str, params: dict | None = None) -> str:
        steps = self._build_plan(goal)
        return json.dumps(steps, indent=2)

    def _vectorize(self, text: str) -> list[float]:
        tokens = self._tokenize(text)
        if not tokens:
            return [0.0] * self._VECTOR_SIZE

        accumulator = [0.0] * self._VECTOR_SIZE
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(0, len(digest), 2):
                slot = digest[index] % self._VECTOR_SIZE
                magnitude = digest[index + 1] / 255.0
                accumulator[slot] += magnitude

        norm = math.sqrt(sum(value * value for value in accumulator)) or 1.0
        return [value / norm for value in accumulator]

    def _tokenize(self, text: str) -> list[str]:
        return [token for token in re.split(r"[^a-z0-9]+", text.lower()) if token]

    def _build_plan(self, goal: str) -> list[dict[str, str | bool]]:
        cleaned_goal = goal.strip() or "Unspecific objective"
        segments = self._segments(cleaned_goal)
        payload_goal = json.dumps({"goal": cleaned_goal}, ensure_ascii=False, indent=2)

        actions: list[dict[str, str | bool]] = [
            {
                "name": "clarify_context",
                "payload": payload_goal,
                "sensitive": False,
                "preview_required": False,
            }
        ]

        for index, segment in enumerate(segments, start=1):
            payload = json.dumps({"step": index, "task": segment}, ensure_ascii=False, indent=2)
            actions.append(
                {
                    "name": "execute_subtask",
                    "payload": payload,
                    "sensitive": False,
                    "preview_required": True,
                }
            )

        summary_payload = json.dumps({"goal": cleaned_goal, "steps": len(segments)}, ensure_ascii=False, indent=2)
        actions.append(
            {
                "name": "summarize_outcome",
                "payload": summary_payload,
                "sensitive": False,
                "preview_required": False,
            }
        )

        return actions

    def _segments(self, goal: str) -> list[str]:
        sentences = [
            sentence.strip()
            for sentence in re.split(r"[\.;\n]+", goal)
            if sentence.strip()
        ]
        if sentences:
            return sentences
        return [goal]


class ModelAdapter:
    def __init__(self, *, url: str | None = None) -> None:
        self._url_override = url
        self._rule_adapter = _RuleBasedAdapter()

    async def _call_runtime(self, base_url: str, path: str, payload: dict, timeout: float) -> dict:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{base_url}{path}",
                    json=payload,
                    timeout=timeout,
                )
                response.raise_for_status()
        except httpx.RequestError as exc:
            message = (
                f"Unable to reach the automation runtime at {base_url}. "
                "Launch the OnDeviceAI app (or run `python automation_daemon.py`) and try again."
            )
            raise RuntimeError(message) from exc
        except httpx.HTTPStatusError as exc:
            detail_payload: object = exc.response.text
            try:
                detail_payload = exc.response.json()
            except Exception:
                pass
            detail = (
                detail_payload
                if isinstance(detail_payload, str)
                else json.dumps(detail_payload, default=str)
            )
            raise RuntimeError(
                f"Runtime request failed with HTTP {exc.response.status_code}: {detail}"
            ) from exc

        try:
            return response.json()
        except Exception as exc:
            raise RuntimeError("Runtime returned invalid JSON payload.") from exc

    def _mode(self) -> str:
        config = get_config()
        return str(config.get("model", {}).get("mode", "ml"))

    def _runtime_url(self) -> str:
        if self._url_override:
            return self._url_override
        config = get_config()
        return str(config.get("model", {}).get("runtime_url", "http://127.0.0.1:9000"))

    async def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self._mode() != "ml":
            return await self._rule_adapter.embed(texts)

        data = await self._call_runtime(self._runtime_url(), "/embed", {"texts": texts}, timeout=60)
        vectors = data.get("vectors", [])
        if isinstance(vectors, Iterable):
            return list(vectors)
        return []

    async def predict(self, prompt: str, params: dict | None = None) -> str:
        if self._mode() != "ml":
            return await self._rule_adapter.predict(prompt, params or {})

        data = await self._call_runtime(
            self._runtime_url(),
            "/predict",
            {"prompt": prompt, "params": params or {}},
            timeout=120,
        )
        return data.get("text", "")
