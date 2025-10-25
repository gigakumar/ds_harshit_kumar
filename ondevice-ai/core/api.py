"""FastAPI REST server wrapping the local Orchestrator and system modules.

Endpoints:
- POST /api/index {text, source}
- POST /api/query {query, k}
- POST /api/plan {goal}
- POST /api/execute {name, payload, sensitive, preview_required}
- GET  /api/logs?limit=100
- GET  /api/plugins
- GET  /api/permissions
- POST /api/permissions {file_access, calendar_access, mail_access}
- GET  /api/model
- POST /api/model {profile, runtime_url?, backend?, settings?}
- POST /api/schedule {name, every_seconds, goal|action}

Also serves the built web UI from ../web/dist if present.
"""
from fastapi import FastAPI, HTTPException, Request  # type: ignore[reportMissingImports]
from fastapi.responses import JSONResponse, FileResponse  # type: ignore[reportMissingImports]
from fastapi.middleware.cors import CORSMiddleware  # type: ignore[reportMissingImports]
from fastapi.staticfiles import StaticFiles  # type: ignore[reportMissingImports]
from pydantic import BaseModel  # type: ignore[reportMissingImports]
import os, sys, json, asyncio
from typing import Optional, List, Dict, Any

from core.orchestrator import Orchestrator
from core.audit import write_event, read_events
from core.config import get_config, save_config, list_model_profiles, apply_model_profile

try:
    # Optional modules (scheduler, plugins, indexer)
    from core.scheduler import Scheduler
except Exception:
    Scheduler = None  # type: ignore

try:
    from core.plugin_runtime import PluginRuntime
except Exception:
    PluginRuntime = None  # type: ignore


app = FastAPI(title="OnDevice AI API", version="0.1.0")

# Dev CORS for Vite
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orch = Orchestrator()
sch = Scheduler() if Scheduler else None
plugin_rt = PluginRuntime() if PluginRuntime else None
_config = get_config()
_permissions_state: Dict[str, bool] = {
    "file_access": bool(_config.get("permissions", {}).get("file_access", False)),
    "calendar_access": bool(_config.get("permissions", {}).get("calendar_access", False)),
    "mail_access": bool(_config.get("permissions", {}).get("mail_access", False)),
}


class IndexReq(BaseModel):
    text: str
    source: str = "api"


@app.post("/api/index")
async def api_index(req: IndexReq):
    doc_id = await orch.index_text(req.text, source=req.source)
    write_event({"type": "index", "source": req.source, "doc_id": doc_id})
    return {"doc_id": doc_id}


class QueryReq(BaseModel):
    query: str
    k: int = 5


@app.post("/api/query")
async def api_query(req: QueryReq):
    hits = await orch.query(req.query, k=req.k)
    write_event({"type": "query", "query": req.query, "k": req.k, "hits": len(hits)})
    return {"hits": hits}


class PlanReq(BaseModel):
    goal: str
    params: Optional[Dict[str, Any]] = None


@app.post("/api/plan")
async def api_plan(req: PlanReq):
    actions = await orch.plan(req.goal, params=req.params)
    write_event({"type": "plan", "goal": req.goal, "actions": actions, "params": req.params or {}})
    return {"actions": actions}


class ExecuteReq(BaseModel):
    name: str
    payload: Optional[Dict[str, Any]] = None
    sensitive: bool = False
    preview_required: bool = False


class PermissionsReq(BaseModel):
    file_access: Optional[bool] = None
    calendar_access: Optional[bool] = None
    mail_access: Optional[bool] = None


class ModelUpdateReq(BaseModel):
    profile: str
    runtime_url: Optional[str] = None
    backend: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None


@app.post("/api/execute")
async def api_execute(req: ExecuteReq):
    # Write audit first
    write_event({
        "type": "action_execute",
        "name": req.name,
        "payload": req.payload or {},
        "sensitive": req.sensitive,
        "preview_required": req.preview_required,
    })
    # Try to execute via plugin runtime if available
    if plugin_rt and getattr(plugin_rt, "enabled", False):
        try:
            result = await plugin_rt.execute(req.name, req.payload or {})
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {"status": "ok", "result": result}
    return {"status": "recorded", "detail": "Plugin runtime disabled"}


@app.get("/api/plugins")
async def api_plugins():
    # List YAML manifests in plugins/ directory
    pdir = os.path.join(os.path.dirname(__file__), os.pardir, "plugins")
    pdir = os.path.abspath(pdir)
    items: List[Dict[str, Any]] = []
    if os.path.isdir(pdir):
        for name in os.listdir(pdir):
            path = os.path.join(pdir, name)
            if name.endswith(".yaml") or name.endswith(".yml"):
                try:
                    import yaml  # type: ignore[import-untyped]
                    with open(path, "r") as f:
                        data = yaml.safe_load(f) or {}
                    data["_file"] = os.path.basename(path)
                    items.append(data)
                except Exception:
                    continue
    return {"plugins": items}


@app.get("/api/logs")
async def api_logs(limit: int = 100):
    items = list(read_events())
    if limit:
        items = items[-int(limit):]
    return {"events": items}


@app.get("/api/permissions")
async def api_permissions():
    return {"permissions": _permissions_state}


@app.post("/api/permissions")
async def api_permissions_update(req: PermissionsReq):
    global _permissions_state
    updated = dict(_permissions_state)
    data = req.model_dump(exclude_none=True)
    for key, value in data.items():
        updated[key] = bool(value)
    _permissions_state = updated
    cfg = get_config()
    cfg.setdefault("permissions", {}).update(_permissions_state)
    save_config(cfg)
    write_event({"type": "permissions_update", "permissions": _permissions_state})
    return {"permissions": _permissions_state}


@app.get("/api/model")
async def api_model_config():
    cfg = get_config()
    model_cfg = cfg.get("model", {})
    profiles = list_model_profiles(cfg)
    active_profile = model_cfg.get("profile")
    for profile in profiles:
        profile["selected"] = profile.get("id") == active_profile
    return {
        "profile": active_profile,
        "backend": model_cfg.get("backend"),
        "runtime_url": model_cfg.get("runtime_url"),
        "profiles": profiles,
    }


@app.post("/api/model")
async def api_model_update(req: ModelUpdateReq):
    overrides: Dict[str, Any] = {}
    if req.runtime_url:
        overrides["runtime_url"] = req.runtime_url
    if req.backend:
        overrides["backend"] = req.backend
    if req.settings:
        overrides.update(req.settings)
    try:
        cfg = apply_model_profile(req.profile, overrides or None)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    model_cfg = cfg.get("model", {})
    write_event({"type": "model_profile_update", "profile": req.profile, "backend": model_cfg.get("backend")})
    profiles = list_model_profiles(cfg)
    for profile in profiles:
        profile["selected"] = profile.get("id") == model_cfg.get("profile")
    return {
        "profile": model_cfg.get("profile"),
        "backend": model_cfg.get("backend"),
        "runtime_url": model_cfg.get("runtime_url"),
        "profiles": profiles,
    }


class ScheduleReq(BaseModel):
    name: str
    every_seconds: int
    goal: Optional[str] = None
    action: Optional[ExecuteReq] = None


@app.post("/api/schedule")
async def api_schedule(req: ScheduleReq):
    if not sch:
        raise HTTPException(status_code=501, detail="Scheduler not available")
    # Job callable
    async def job():
        if req.goal:
            acts = await orch.plan(req.goal)
            for a in acts:
                if plugin_rt and getattr(plugin_rt, "enabled", False):
                    await plugin_rt.execute(a.get("name", ""), json.loads(a.get("payload", "{}")))
        elif req.action:
            if plugin_rt and getattr(plugin_rt, "enabled", False):
                await plugin_rt.execute(req.action.name, req.action.payload or {})
        write_event({"type": "schedule_run", "name": req.name})

    sch.add_interval_job(req.name, job, seconds=req.every_seconds)
    write_event({"type": "schedule_add", "name": req.name, "every_seconds": req.every_seconds})
    return {"status": "scheduled"}


# Static web UI
# Detect packaged environment (PyInstaller) to locate web/dist
_base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if getattr(sys, "_MEIPASS", None):
    _base_dir = sys._MEIPASS  # type: ignore[attr-defined]
WEB_DIST = os.path.abspath(os.path.join(_base_dir, "web", "dist"))
if os.path.isdir(WEB_DIST):
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")
else:
     WEB_STATIC = os.path.abspath(os.path.join(_base_dir, "web", "static"))
     if os.path.isdir(WEB_STATIC):
          app.mount("/", StaticFiles(directory=WEB_STATIC, html=True), name="web-static")


def main():
    import uvicorn  # type: ignore[import-untyped]
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
