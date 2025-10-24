"""Simple JSONL audit log writer and reader."""
import json, os, time
from typing import Any, Dict, Iterable

DEFAULT_LOG = os.environ.get("ONDEVICE_AUDIT_LOG", "/tmp/ondevice_audit.jsonl")

def write_event(event: Dict[str, Any], path: str = DEFAULT_LOG) -> None:
    evt = dict(event)
    evt.setdefault("ts", int(time.time()))
    os.makedirs(os.path.dirname(path), exist_ok=True) if os.path.dirname(path) else None
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(evt, ensure_ascii=False) + "\n")

def read_events(path: str = DEFAULT_LOG) -> Iterable[Dict[str, Any]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except Exception:
                continue
