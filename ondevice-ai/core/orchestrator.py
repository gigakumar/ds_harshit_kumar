# core/orchestrator.py
from __future__ import annotations

import asyncio
import json
from typing import Any, Optional, List, Dict

import numpy as np  # type: ignore[reportMissingImports]

from core.config import get_config
from core.model_adapter import ModelAdapter
from core.vector_store import VectorStore

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
        vectors = await self.model.embed([text])
        if vectors:
            vector = np.array(vectors[0], dtype=np.float32)
            self.store.insert_embedding(doc_id, vector)
        return doc_id

    async def query(self, q, k=5):
        vectors = await self.model.embed([q])
        if not vectors:
            return []
        qv = np.array(vectors[0], dtype=np.float32)
        rows = self.store.all_embeddings()
        scored=[]
        for _, v, doc_id in rows:
            scored.append((self.cosine(np.array(qv), v), doc_id))
        scored.sort(reverse=True, key=lambda x:x[0])
        hits=[]
        for score, doc_id in scored[:k]:
            meta = self.store.get_doc_meta(doc_id)
            if meta:
                hits.append({
                    "doc_id": doc_id,
                    "score": score,
                    "text": meta.get("text"),
                    "meta": meta.get("meta"),
                })
            else:
                hits.append({"doc_id": doc_id, "score": score, "text": self.store.get_doc(doc_id)})
        return hits

    async def plan(self, goal, params: Optional[dict] = None):
        config = get_config()
        mode = config.get("model", {}).get("mode", "ml")
        if mode != "ml":
            # Rule-based adapter already returns serialized JSON
            txt = await self.model.predict(goal, params=params or {})
        else:
            prompt = (
                "You are a local assistant. Create a step-by-step plan of actions to achieve: "
                f"{goal}\nReturn JSON array of actions: {{name, payload, sensitive, preview_required}}"
            )
            plan_params = dict(params or {})
            if "max_tokens" not in plan_params:
                plan_params = dict(plan_params)
                plan_params["max_tokens"] = 256
            txt = await self.model.predict(prompt, params=plan_params)

        try:
            actions = json.loads(txt)
        except Exception:
            actions = [{
                "name": "note",
                "payload": json.dumps({"text": txt}),
                "sensitive": False,
                "preview_required": False,
            }]
        return actions

    async def list_documents(self, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
        return self.store.list_docs(limit=limit)

    async def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        meta = self.store.get_doc_meta(doc_id)
        if not meta:
            return None
        return meta

    async def delete_document(self, doc_id: str) -> bool:
        return self.store.delete_doc(doc_id)

    async def clear_documents(self) -> None:
        self.store.clear()

    async def document_stats(self) -> Dict[str, Any]:
        return {
            "count": self.store.count_docs(),
        }
