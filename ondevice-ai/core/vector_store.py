# core/vector_store.py
import os
import sqlite3
import msgpack
import uuid
import time
from datetime import datetime, timezone
import numpy as np
from typing import Iterable, List, Tuple, Optional, Dict, Any

class VectorStore:
    def __init__(self, path: Optional[str] = None):
        default_path = path or os.path.join(os.path.expanduser("~"), ".mahi", "vector_store.db")
        os.makedirs(os.path.dirname(default_path), exist_ok=True)
        self.db = sqlite3.connect(default_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cur = self.db.cursor()
        cur.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS docs(
            id TEXT PRIMARY KEY,
            source TEXT,
            ts INTEGER,
            text TEXT,
            tokens INTEGER,
            preview TEXT
        );
        CREATE TABLE IF NOT EXISTS embeddings(id TEXT PRIMARY KEY, doc_id TEXT, vec BLOB);
        """)
        self.db.commit()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self.db.cursor()
        columns = {row[1] for row in cur.execute("PRAGMA table_info(docs)")}
        if "tokens" not in columns:
            cur.execute("ALTER TABLE docs ADD COLUMN tokens INTEGER")
        if "preview" not in columns:
            cur.execute("ALTER TABLE docs ADD COLUMN preview TEXT")
        self.db.commit()

    def add(self, text: str, source: str = "cli") -> str:
        doc_id = str(uuid.uuid4())
        ts = int(time.time())
        tokens = self._estimate_tokens(text)
        preview = text[:200]
        cur = self.db.cursor()
        cur.execute(
            "INSERT INTO docs(id,source,ts,text,tokens,preview) VALUES (?,?,?,?,?,?)",
            (doc_id, source, ts, text, tokens, preview),
        )
        self.db.commit()
        return doc_id

    def insert_embedding(self, doc_id: str, vec: np.ndarray) -> None:
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
        r = cur.execute("SELECT id, source, ts, text FROM docs WHERE id= ?", (doc_id,)).fetchone()
        if not r:
            return None
        return r["text"]

    def get_doc_meta(self, doc_id: str) -> Optional[Dict[str, Any]]:
        cur = self.db.cursor()
        row = cur.execute(
            "SELECT id, source, ts, text, tokens, preview FROM docs WHERE id = ?",
            (doc_id,),
        ).fetchone()
        if not row:
            return None
        text = row[3] or ""
        tokens = row[4]
        preview = row[5]
        if tokens is None or preview is None:
            tokens, preview = self._ensure_tokens_preview(row[0], tokens, preview)
            if not text:
                stored = self.get_doc(row[0]) or ""
                text = stored
        return {
            "id": row[0],
            "text": text,
            "meta": {
                "source": row[1],
                "ts": row[2],
                "created_at": self._format_ts(row[2]),
                "tokens": tokens,
                "preview": preview,
            },
        }

    def list_docs(self, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        query = "SELECT id, source, ts, tokens, preview FROM docs ORDER BY ts DESC"
        if limit and limit > 0:
            query += " LIMIT ?"
            params: Iterable[Any] = (limit,)
            rows = self.db.cursor().execute(query, params).fetchall()
        else:
            rows = self.db.cursor().execute(query).fetchall()
        docs: List[Dict[str, Any]] = []
        for row in rows:
            doc_id = row[0]
            tokens, preview = self._ensure_tokens_preview(doc_id, row[3], row[4])
            docs.append(
                {
                    "id": doc_id,
                    "meta": {
                        "source": row[1],
                        "ts": row[2],
                        "created_at": self._format_ts(row[2]),
                        "tokens": tokens,
                        "preview": preview,
                    },
                }
            )
        return docs

    def delete_doc(self, doc_id: str) -> bool:
        cur = self.db.cursor()
        res = cur.execute("DELETE FROM docs WHERE id = ?", (doc_id,))
        cur.execute("DELETE FROM embeddings WHERE doc_id = ?", (doc_id,))
        self.db.commit()
        return res.rowcount > 0

    def clear(self) -> None:
        cur = self.db.cursor()
        cur.execute("DELETE FROM docs")
        cur.execute("DELETE FROM embeddings")
        self.db.commit()

    def count_docs(self) -> int:
        cur = self.db.cursor()
        row = cur.execute("SELECT COUNT(*) FROM docs").fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        if not text:
            return 0
        return len(text.split())

    def _ensure_tokens_preview(self, doc_id: str, tokens: Optional[int], preview: Optional[str]) -> Tuple[int, str]:
        if tokens is not None and preview is not None:
            return int(tokens), preview
        cur = self.db.cursor()
        row = cur.execute("SELECT text FROM docs WHERE id = ?", (doc_id,)).fetchone()
        text = row["text"] if row else ""
        calc_tokens = int(tokens) if tokens is not None else self._estimate_tokens(text)
        calc_preview = preview if preview is not None else (text or "")[:200]
        cur.execute(
            "UPDATE docs SET tokens = ?, preview = ? WHERE id = ?",
            (calc_tokens, calc_preview, doc_id),
        )
        self.db.commit()
        return calc_tokens, calc_preview

    @staticmethod
    def _format_ts(ts: Optional[int]) -> Optional[str]:
        if ts is None:
            return None
        try:
            stamp = datetime.fromtimestamp(int(ts), tz=timezone.utc)
            iso = stamp.isoformat().replace("+00:00", "Z")
            return iso
        except Exception:
            return None
