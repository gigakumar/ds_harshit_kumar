import asyncio
import json
from pathlib import Path

import numpy as np

from core.orchestrator import Orchestrator
from core.vector_store import VectorStore


class StubModel:
    async def embed(self, texts):
        vectors = []
        for text in texts:
            vec = np.zeros(4, dtype=np.float32)
            vec[0] = float(len(text))
            vec[1] = float(sum(ord(ch) for ch in text) % 17)
            vectors.append(vec.tolist())
        return vectors

    async def predict(self, prompt, params=None):
        return json.dumps([
            {"name": "step", "payload": json.dumps({"prompt": prompt}), "sensitive": False, "preview_required": False}
        ])


def test_orchestrator_flow(tmp_path):
    db_path = tmp_path / "orch.db"
    orchestrator = Orchestrator(store=VectorStore(path=str(db_path)), model=StubModel())

    doc_id = asyncio.run(orchestrator.index_text("stub text", source="unit"))
    assert doc_id

    hits = asyncio.run(orchestrator.query("stub", k=3))
    assert hits and hits[0]["doc_id"] == doc_id

    plan = asyncio.run(orchestrator.plan("test goal"))
    assert isinstance(plan, list) and plan[0]["name"] == "step"
