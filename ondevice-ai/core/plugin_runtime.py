import platform, subprocess, json, os, sys
from typing import Dict, Any, Optional
from core.plugins import PluginManifest
from tools.agent_browser import get_browser, AgentBrowserError  # optional dependency handled lazily


class CapabilityError(Exception):
    pass


class PluginRuntime:
    """Executes a minimal set of safe, whitelisted AppleScript-based actions.

    Capabilities are loaded from plugins/plugin-manifest.yaml and enforced per action.
    """

    def __init__(self, manifest_path: 'str | None' = None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
        if getattr(sys, "_MEIPASS", None):
            base_dir = sys._MEIPASS  # type: ignore[attr-defined]
        default_manifest = os.path.join(base_dir, "plugins", "plugin-manifest.yaml")
        path = manifest_path or default_manifest
        if os.path.isfile(path):
            try:
                self.manifest: Optional[PluginManifest] = PluginManifest.load(path)
                self.capabilities = set(self.manifest.capabilities)
                self.enabled = True
            except Exception:
                self.manifest = None
                self.capabilities = set()
                self.enabled = False
        else:
            self.manifest = None
            self.capabilities = set()
            self.enabled = False

    async def execute(self, name: str, payload: Dict[str, Any]):
        handlers = {
            "open_finder": ("finder", self._open_finder),
            "create_note": ("notes", self._create_note),
            "create_calendar_event": ("calendar", self._create_calendar_event),
            "compose_mail": ("mail", self._compose_mail),
            # Agentic browser entrypoint: payload requires {op: ..., ...}
            "browser": ("browser", self._browser_action),
        }
        if name not in handlers:
            raise CapabilityError(f"Unknown action: {name}")
        cap, fn = handlers[name]
        if not self.enabled:
            raise CapabilityError("Plugin runtime disabled; missing or invalid manifest")
        if self.capabilities and cap not in self.capabilities:
            raise CapabilityError(f"Capability not allowed by manifest: {cap}")
        return await fn(payload)

    async def _run_osascript(self, script: str) -> str:
        if platform.system() != "Darwin":
            # No-op on non-macOS systems
            return "noop"
        res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(res.stderr.strip() or "osascript failed")
        return (res.stdout or "").strip()

    async def _open_finder(self, payload: Dict[str, Any]):
        path = payload.get("path", "~/")
        script = f'tell application "Finder" to open POSIX file (POSIX path of (do shell script "printf %s \'{path}\'"))'
        return await self._run_osascript(script)

    async def _browser_action(self, payload: Dict[str, Any]):
        op = str(payload.get("op", "")).strip().lower()
        args = dict(payload)
        try:
            br = get_browser()
            result = br.run(op, **args)
            return result
        except AgentBrowserError as e:
            raise CapabilityError(str(e))
        except Exception as e:  # pragma: no cover - best-effort
            raise CapabilityError(f"browser action failed: {e}")

    async def _create_note(self, payload: Dict[str, Any]):
        title = (payload.get("title") or "Note")[:120]
        body = payload.get("body") or ""
        script = (
            'tell application "Notes"\n'
            f'  make new note at folder "iCloud" with properties {{name:"{title}", body:"{body}"}}\n'
            'end tell'
        )
        return await self._run_osascript(script)

    async def _create_calendar_event(self, payload: Dict[str, Any]):
        title = (payload.get("title") or "Event")[:120]
        start = payload.get("start") or "today"
        duration_minutes = int(payload.get("duration_minutes") or 30)
        script = (
            'tell application "Calendar"\n'
            '  tell calendar 1\n'
            f'    make new event with properties {{summary:"{title}", start date:(date "{start}"), end date:(date "{start}") + {duration_minutes} * minutes}}\n'
            '  end tell\n'
            'end tell'
        )
        return await self._run_osascript(script)

    async def _compose_mail(self, payload: Dict[str, Any]):
        to = payload.get("to") or ""
        subject = (payload.get("subject") or "")[:120]
        body = payload.get("body") or ""
        script = (
            'tell application "Mail"\n'
            '  set newMessage to make new outgoing message with properties {visible:true}\n'
            f'  tell newMessage to set subject to "{subject}"\n'
            f'  tell newMessage to set content to "{body}"\n'
            f'  tell newMessage to make new to recipient at end of to recipients with properties {{address:"{to}"}}\n'
            '  activate\n'
            'end tell'
        )
        return await self._run_osascript(script)
