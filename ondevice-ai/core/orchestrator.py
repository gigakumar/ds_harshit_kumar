# core/orchestrator.py
import numpy as np
from core.vector_store import VectorStore
from core.model_adapter import ModelAdapter
import asyncio, json
from typing import Optional, Any

class Orchestrator:
    def __init__(self, store: Optional[VectorStore]=None, model: Optional[Any]=None):
        self.store = store or VectorStore()
        self.model = model or ModelAdapter()

    @staticmethod
    def cosine(a,b):
        an = np.linalg.norm(a); bn = np.linalg.norm(b)
        if an==0 or bn==0: return 0.0
        return float(np.dot(a,b)/(an*bn))

    async def index_text(self, text, source="cli"):
        doc_id = self.store.add(text, source)
        vec = (await self.model.embed([text]))[0]
        import numpy as np
        self.store.insert_embedding(doc_id, np.array(vec, dtype=np.float32))
        return doc_id

    async def query(self, q, k=5):
        qv = (await self.model.embed([q]))[0]
        rows = self.store.all_embeddings()
        scored=[]
        for _, v, doc_id in rows:
            scored.append((self.cosine(np.array(qv), v), doc_id))
        scored.sort(reverse=True, key=lambda x:x[0])
        hits=[]
        for score, doc_id in scored[:k]:
            hits.append({"doc_id": doc_id, "score": score, "text": self.store.get_doc(doc_id)})
        return hits

    async def plan(self, goal):
        # deterministic prompt recipe
        prompt = (
            "You are a local assistant. Create a step-by-step plan of actions to achieve: "
            f"{goal}\nReturn JSON array of actions: {{name, payload, sensitive, preview_required}}"
        )
        txt = await self.model.predict(prompt, params={"max_tokens":256})
        # expect txt to be JSON. Fallback: try parse, else simple action
        try:
            actions = json.loads(txt)
        except Exception:
            actions = [{"name":"note","payload":json.dumps({"text":txt}), "sensitive":False, "preview_required":False}]
        return actions
