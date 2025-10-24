# tests/test_vector_store.py
import numpy as np
from core.vector_store import VectorStore

def test_vector_store_insert_and_fetch(tmp_path):
    dbp = tmp_path / "test.db"
    vs = VectorStore(path=str(dbp))
    doc_id = vs.add("hello world", source="test")
    vec = np.ones(8, dtype=np.float32)
    vs.insert_embedding(doc_id, vec)
    allv = vs.all_embeddings()
    assert len(allv) == 1
    _, arr, did = allv[0]
    assert did == doc_id
    assert np.allclose(arr, vec)
    assert vs.get_doc(doc_id) == "hello world"
