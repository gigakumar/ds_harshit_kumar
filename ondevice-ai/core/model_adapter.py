# core/model_adapter.py
import httpx, asyncio

class ModelAdapter:
    def __init__(self, url="http://127.0.0.1:9000"):
        self.url = url

    async def embed(self, texts):
        async with httpx.AsyncClient() as c:
            r = await c.post(self.url + "/embed", json={"texts": texts}, timeout=60)
            r.raise_for_status()
            return r.json()["vectors"]

    async def predict(self, prompt, params=None):
        async with httpx.AsyncClient() as c:
            r = await c.post(self.url + "/predict", json={"prompt": prompt, "params": params or {}}, timeout=120)
            r.raise_for_status()
            return r.json()["text"]
