# tests/test_end2end.py
import asyncio
import numpy as np
from core.orchestrator import Orchestrator
from core.vector_store import VectorStore

class DummyModel:
    async def embed(self, texts):
        # deterministic embedding: length-based vector
        out=[]
        for t in texts:
            rng = np.zeros(8, dtype=np.float32)
            rng[0] = float(len(t))
            out.append(rng.tolist())
        return out
    async def predict(self, prompt, params=None):
        return '[{"name":"note","payload":"{}","sensitive":false,"preview_required":false}]'

async def _run(tmp_path):
    store = VectorStore(path=str(tmp_path/"e2e.db"))
    orch = Orchestrator(store=store, model=DummyModel())
    did = await orch.index_text("alpha document", source="test")
    hits = await orch.query("alpha", k=1)
    assert len(hits) == 1
    assert hits[0]["doc_id"] == did
    actions = await orch.plan("say hello")
    assert isinstance(actions, list) and len(actions) >= 1

def test_end2end_minimal(tmp_path):
    asyncio.run(_run(tmp_path))
