# core/vector_store.py
import sqlite3, msgpack, uuid, time
import numpy as np
from typing import List, Tuple, Optional

class VectorStore:
    def __init__(self, path="/tmp/ondevice_store.db"):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self._init_db()

    def _init_db(self):
        cur = self.db.cursor()
        cur.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY, source TEXT, ts INTEGER, text TEXT);
        CREATE TABLE IF NOT EXISTS embeddings(id TEXT PRIMARY KEY, doc_id TEXT, vec BLOB);
        """)
        self.db.commit()

    def add(self, text: str, source: str="cli") -> str:
        doc_id = str(uuid.uuid4())
        ts = int(time.time())
        cur = self.db.cursor()
        cur.execute("INSERT INTO docs(id,source,ts,text) VALUES (?,?,?,?)", (doc_id, source, ts, text))
        self.db.commit()
        return doc_id

    def insert_embedding(self, doc_id: str, vec: np.ndarray):
        blob = msgpack.packb(vec.astype('float32').tolist())
        cur = self.db.cursor()
        cur.execute("INSERT OR REPLACE INTO embeddings(id,doc_id,vec) VALUES (?,?,?)", (f"emb-{doc_id}", doc_id, blob))
        self.db.commit()

    def all_embeddings(self) -> List[Tuple[str, np.ndarray, str]]:
        cur = self.db.cursor()
        rows = cur.execute("SELECT id,vec,doc_id FROM embeddings").fetchall()
        out=[]
        for id, blob, doc_id in rows:
            arr = np.array(msgpack.unpackb(blob), dtype=np.float32)
            out.append((id, arr, doc_id))
        return out

    def get_doc(self, doc_id: str) -> Optional[str]:
        cur = self.db.cursor()
        r = cur.execute("SELECT text FROM docs WHERE id= ?", (doc_id,)).fetchone()
        return r[0] if r else None
