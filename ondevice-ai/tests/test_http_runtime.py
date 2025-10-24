def test_index_then_query():
    from tools.mlx_runtime import app

    with app.test_client() as client:
        index_resp = client.post("/index", json={"text": "hello world", "source": "test"})
        assert index_resp.status_code == 200
        doc_id = index_resp.json["id"]

        docs_resp = client.get("/documents")
        assert docs_resp.status_code == 200
        assert docs_resp.json["documents"]

        hit_resp = client.post("/query", json={"query": "hello", "limit": 1})
        assert hit_resp.status_code == 200
        hits = hit_resp.json["hits"]
        assert hits and hits[0]["doc_id"] == doc_id

        plan_resp = client.post("/plan", json={"goal": "test"})
        assert plan_resp.status_code == 200
        assert plan_resp.json["actions"]
