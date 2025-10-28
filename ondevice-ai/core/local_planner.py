from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Sequence
from urllib.parse import quote_plus

import numpy as np


_DATASET_DEFAULT = {
    "version": 1,
    "labels": [
        {"id": "shell_command", "examples": ["run `echo hi`"]},
        {"id": "file_write", "examples": ["write notes to notes.txt"]},
        {"id": "file_read", "examples": ["read notes.txt"]},
        {"id": "browser_research", "examples": ["open example.com"]},
        {"id": "app_launch", "examples": ["launch Safari"]},
        {"id": "applescript", "examples": ["run an applescript"]},
    ],
}


@dataclass
class _Sample:
    label: str
    goal: str


class LocalPlannerModel:
    """Lightweight ML planner that classifies goals into action templates."""

    _VECTOR_SIZE = 192

    def __init__(self, dataset_path: str | Path | None = None) -> None:
        self.dataset_path = Path(dataset_path) if dataset_path else self._default_dataset_path()
        self._dataset = self._load_dataset(self.dataset_path)
        self._samples: List[_Sample] = self._build_samples(self._dataset)
        self._centroids: Dict[str, np.ndarray] = self._compute_centroids(self._samples)
        self._labels: List[str] = sorted({sample.label for sample in self._samples})

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        return [self._vectorize(text).tolist() for text in texts]

    def generate(self, prompt: str, **_: Any) -> str:
        goal = self._extract_goal(prompt)
        plan = self.plan(goal)
        return json.dumps(plan)

    def plan(self, goal: str) -> List[Dict[str, Any]]:
        label = self._classify(goal)
        return self._render_plan(label, goal)

    # dataset helpers
    def _default_dataset_path(self) -> Path:
        root = Path(__file__).resolve().parents[1] / "ml_models" / "planner" / "training_data.json"
        return root

    def _load_dataset(self, path: Path) -> Dict[str, Any]:
        if path.exists():
            raw = path.read_text(encoding="utf-8")
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict) and parsed.get("labels"):
                    return parsed
            except Exception:
                pass
        return _DATASET_DEFAULT

    def _build_samples(self, dataset: Dict[str, Any]) -> List[_Sample]:
        samples: List[_Sample] = []
        for entry in dataset.get("labels", []):
            label = entry.get("id")
            if not isinstance(label, str):
                continue
            for goal in entry.get("examples", []) or []:
                if isinstance(goal, str) and goal.strip():
                    samples.append(_Sample(label=label, goal=goal.strip()))
        if not samples:
            samples.append(_Sample(label="shell_command", goal="run `echo hello`"))
        return samples

    def _compute_centroids(self, samples: Sequence[_Sample]) -> Dict[str, np.ndarray]:
        grouped: Dict[str, List[np.ndarray]] = {}
        for sample in samples:
            grouped.setdefault(sample.label, []).append(self._vectorize(sample.goal))
        centroids: Dict[str, np.ndarray] = {}
        for label, vectors in grouped.items():
            stacked = np.vstack(vectors)
            centroid = stacked.mean(axis=0)
            norm = np.linalg.norm(centroid) or 1.0
            centroids[label] = centroid / norm
        return centroids

    # vectorization
    def _tokenize(self, text: str) -> List[str]:
        return [token for token in re.split(r"[^a-z0-9]+", text.lower()) if token]

    def _vectorize(self, text: str) -> np.ndarray:
        tokens = self._tokenize(text)
        if not tokens:
            return np.zeros(self._VECTOR_SIZE, dtype=np.float32)
        buffer = np.zeros(self._VECTOR_SIZE, dtype=np.float32)
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for index in range(0, len(digest), 2):
                slot = digest[index] % self._VECTOR_SIZE
                magnitude = digest[index + 1] / 255.0
                buffer[slot] += magnitude
        norm = math.sqrt(float(np.dot(buffer, buffer))) or 1.0
        return (buffer / norm).astype(np.float32)

    # classification
    def _classify(self, goal: str) -> str:
        vector = self._vectorize(goal)
        if not self._centroids:
            return "shell_command"
        best_label = "shell_command"
        best_score = -1.0
        for label, centroid in self._centroids.items():
            score = float(np.dot(vector, centroid))
            if score > best_score:
                best_score = score
                best_label = label
        if best_score < 0.28 and "shell" not in best_label:
            return "shell_command"
        return best_label

    # render plan
    def _render_plan(self, label: str, goal: str) -> List[Dict[str, Any]]:
        label = label or "shell_command"
        goal = goal.strip() or "perform requested automation"
        if label == "file_write":
            return self._plan_file_write(goal)
        if label == "file_read":
            return self._plan_file_read(goal)
        if label == "browser_research":
            return self._plan_browser(goal)
        if label == "app_launch":
            return self._plan_app_launch(goal)
        if label == "applescript":
            return self._plan_applescript(goal)
        return self._plan_shell(goal)

    # plan templates
    def _plan_shell(self, goal: str) -> List[Dict[str, Any]]:
        command = self._extract_command(goal) or f"echo \"{goal}\""
        payload = {
            "command": command,
            "shell": True,
        }
        return [
            {
                "name": "system.shell.run",
                "payload": json.dumps(payload),
                "sensitive": False,
                "preview_required": True,
            }
        ]

    def _plan_file_write(self, goal: str) -> List[Dict[str, Any]]:
        path = self._extract_path(goal) or "notes.txt"
        content = self._infer_content(goal)
        write_payload = {
            "path": path,
            "content": content,
            "append": "append" in goal.lower(),
        }
        read_payload = {
            "path": path,
        }
        return [
            {
                "name": "system.files.write",
                "payload": json.dumps(write_payload),
                "sensitive": False,
                "preview_required": True,
            },
            {
                "name": "system.files.read",
                "payload": json.dumps(read_payload),
                "sensitive": False,
                "preview_required": False,
            },
        ]

    def _plan_file_read(self, goal: str) -> List[Dict[str, Any]]:
        path = self._extract_path(goal) or "README.md"
        payload = {"path": path}
        return [
            {
                "name": "system.files.read",
                "payload": json.dumps(payload),
                "sensitive": False,
                "preview_required": False,
            }
        ]

    def _plan_browser(self, goal: str) -> List[Dict[str, Any]]:
        url = self._extract_url(goal)
        if not url:
            search_q = quote_plus(goal)
            url = f"https://www.google.com/search?q={search_q}"
        navigate = {"url": url}
        extract = {"selector": "body"}
        return [
            {
                "name": "browser.navigate",
                "payload": json.dumps(navigate),
                "sensitive": False,
                "preview_required": False,
            },
            {
                "name": "browser.extract",
                "payload": json.dumps(extract),
                "sensitive": False,
                "preview_required": False,
            },
        ]

    def _plan_app_launch(self, goal: str) -> List[Dict[str, Any]]:
        app = self._extract_application(goal) or "Finder"
        payload = {"application": app}
        return [
            {
                "name": "system.apps.launch",
                "payload": json.dumps(payload),
                "sensitive": False,
                "preview_required": False,
            }
        ]

    def _plan_applescript(self, goal: str) -> List[Dict[str, Any]]:
        script = self._extract_script(goal)
        payload = {"script": script}
        return [
            {
                "name": "system.apple_script.run",
                "payload": json.dumps(payload),
                "sensitive": True,
                "preview_required": True,
            }
        ]

    # extraction helpers
    def _extract_goal(self, prompt: str) -> str:
        if not prompt:
            return ""
        match = re.search(r"Goal:\s*(.+)", prompt, flags=re.IGNORECASE | re.DOTALL)
        if match:
            captured = match.group(1).strip()
            for delimiter in ("\n\n", "\nACTION", "\nAvailable"):
                idx = captured.find(delimiter)
                if idx != -1:
                    captured = captured[:idx].strip()
            return captured
        return prompt.strip()

    def _extract_command(self, goal: str) -> str | None:
        backtick = re.search(r"`([^`]+)`", goal)
        if backtick:
            return backtick.group(1).strip()
        quoted = re.search(r'"([^"]+)"', goal)
        if quoted:
            return quoted.group(1).strip()
        after_keywords = re.search(r"(?:run|execute)\s+([a-z0-9_\-./\s]+)", goal, flags=re.IGNORECASE)
        if after_keywords:
            return " ".join(after_keywords.group(1).split()).strip()
        return None

    def _extract_path(self, goal: str) -> str | None:
        path_match = re.search(r"(/?[\w\-/]+\.[a-z0-9]{1,6})", goal, flags=re.IGNORECASE)
        if path_match:
            return path_match.group(1)
        directory = re.search(r"(/?[\w\-/]+/)", goal)
        if directory:
            name = "notes.txt"
            return f"{directory.group(1).rstrip('/')}/{name}"
        return None

    def _infer_content(self, goal: str) -> str:
        cleaned = goal.strip().rstrip(".")
        if len(cleaned) > 200:
            cleaned = cleaned[:200] + "…"
        return f"## Auto-generated note\n{cleaned}\n"

    def _extract_url(self, goal: str) -> str | None:
        match = re.search(r"https?://[\w\-._~:/?#\[\]@!$&'()*+,;=%]+", goal)
        if match:
            return match.group(0)
        www = re.search(r"www\.[\w\-._~:/?#]+", goal)
        if www:
            return f"https://{www.group(0)}"
        return None

    def _extract_application(self, goal: str) -> str | None:
        match = re.search(r"launch\s+([A-Z][A-Za-z0-9\s]+)", goal)
        if match:
            return match.group(1).strip()
        match = re.search(r"open\s+([A-Z][A-Za-z0-9\s]+)", goal)
        if match:
            return match.group(1).strip()
        match = re.search(r"([A-Z][A-Za-z0-9\s]+)\s+app", goal)
        if match:
            return match.group(1).strip()
        return None

    def _extract_script(self, goal: str) -> str:
        backtick = re.search(r"`([^`]+)`", goal)
        if backtick:
            return backtick.group(1).strip()
        script_match = re.search(r'tell\s+application[^"]+', goal, flags=re.IGNORECASE)
        if script_match:
            return script_match.group(0)
        return "tell application \"System Events\" to display dialog \"Automation task complete\""


__all__ = ["LocalPlannerModel"]
