from importlib import reload
from textwrap import dedent


def test_index_then_query():
    from tools.mlx_runtime import app

    with app.test_client() as client:
        index_resp = client.post("/index", json={"text": "hello world", "source": "test"})
        assert index_resp.status_code == 200
        doc_id = index_resp.get_json()["id"]

        docs_resp = client.get("/documents")
        assert docs_resp.status_code == 200
        assert docs_resp.get_json()["documents"]

        hit_resp = client.post("/query", json={"query": "hello", "limit": 1})
        assert hit_resp.status_code == 200
        hits = hit_resp.get_json()["hits"]
        assert hits and hits[0]["doc_id"] == doc_id

        plan_resp = client.post("/plan", json={"goal": "test"})
        assert plan_resp.status_code == 200
        assert plan_resp.get_json()["actions"]


def test_permissions_roundtrip(tmp_path, monkeypatch):
    cfg_path = tmp_path / "automation.yaml"
    cfg_path.write_text(
        dedent(
            """
            model:
              backend: mlx
            permissions:
              file_access: false
              calendar_access: false
              mail_access: false
            """
        )
    )
    monkeypatch.setenv("MAHI_CONFIG", str(cfg_path))

    import tools.mlx_runtime as runtime

    reload(runtime)

    with runtime.app.test_client() as client:
        resp = client.get("/permissions")
        assert resp.status_code == 200
        assert resp.get_json()["permissions"]["file_access"] is False

        update = client.post("/permissions", json={"file_access": True})
        assert update.status_code == 200
        assert update.get_json()["permissions"]["file_access"] is True

        cfg_data = cfg_path.read_text()
        assert "file_access: true" in cfg_data.lower()

    reload(runtime)


def test_model_profiles(tmp_path, monkeypatch):
    cfg_path = tmp_path / "automation.yaml"
    cfg_path.write_text(
        dedent(
            """
            model:
              profile: mlx_local
              backend: mlx
              runtime_url: http://127.0.0.1:9000
              profiles:
                - id: mlx_local
                  label: Local
                  backend: mlx
                  description: Local bundled model
                  capabilities: [offline]
                  settings:
                    mlx:
                      model_path: bundle://mock
                - id: ollama_remote
                  label: Remote Ollama
                  backend: ollama
                  description: Remote host
                  capabilities: [remote]
                  settings:
                    ollama:
                      host: http://127.0.0.1:11434
                      model: llama3
              mlx:
                model_path: bundle://mock
                model_name: local
              ollama:
                host: http://127.0.0.1:11434
                model: llama3
            permissions:
              file_access: false
              calendar_access: false
              mail_access: false
            """
        )
    )
    monkeypatch.setenv("MAHI_CONFIG", str(cfg_path))

    import tools.mlx_runtime as runtime

    reload(runtime)

    with runtime.app.test_client() as client:
        resp = client.get("/model")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["profile"] == "mlx_local"
        assert data["mode"] == "ml"
        assert len(data["profiles"]) == 2

        update = client.post("/model", json={"profile": "ollama_remote"})
        assert update.status_code == 200
        updated = update.get_json()
        assert updated["profile"] == "ollama_remote"
        assert any(p["selected"] for p in updated["profiles"] if p["id"] == "ollama_remote")

    rendered = cfg_path.read_text()
    assert "profile: ollama_remote" in rendered

    reload(runtime)


def test_model_mode_toggle(tmp_path, monkeypatch):
    cfg_path = tmp_path / "automation.yaml"
    cfg_path.write_text(
        dedent(
            """
            model:
              profile: mlx_local
              backend: mlx
              runtime_url: http://127.0.0.1:9000
              modes:
                - id: ml
                  label: Machine Learning
                - id: rules
                  label: Rules Engine
              profiles: []
            permissions:
              file_access: false
              calendar_access: false
              mail_access: false
            """
        )
    )
    monkeypatch.setenv("MAHI_CONFIG", str(cfg_path))

    import tools.mlx_runtime as runtime

    reload(runtime)

    with runtime.app.test_client() as client:
        resp = client.get("/model")
        assert resp.status_code == 200
        assert resp.get_json()["mode"] == "ml"

        toggle = client.post("/model", json={"mode": "rules"})
        assert toggle.status_code == 200
        assert toggle.get_json()["mode"] == "rules"

        roundtrip = client.get("/model")
        assert roundtrip.get_json()["mode"] == "rules"

    reload(runtime)
