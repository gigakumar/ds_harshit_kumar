from __future__ import annotations

import asyncio
import base64
import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional

from core.sandbox import SandboxAction, SandboxHarness, SandboxPermissions

try:  # Optional dependency
    from tools.agent_browser import AgentBrowserError, get_browser
except Exception:  # pragma: no cover - fallback when Playwright is unavailable
    AgentBrowserError = RuntimeError  # type: ignore[assignment]

    def get_browser() -> Any:  # type: ignore[override]
        raise AgentBrowserError("Agentic browser helpers are unavailable; install Playwright support")


class CapabilityError(Exception):
    """Raised when an automation action cannot be fulfilled because of manifest or permission limits."""


@dataclass(frozen=True)
class SystemActionSpec:
    """Declarative metadata for a system automation action."""

    name: str
    capability: str
    permissions: tuple[str, ...]
    handler: Callable[[Dict[str, Any]], Any]
    summary: str = ""
    uses_sandbox: bool = False
    sensitive: bool = False
    preview_required: bool = False

    async def invoke(self, payload: Dict[str, Any]) -> Any:
        result = self.handler(payload)
        if asyncio.iscoroutine(result):
            return await result
        return result


class SystemAgent:
    """Dispatches high-level automation actions against the local operating system."""

    def __init__(
        self,
        *,
        sandbox: SandboxHarness,
        permissions: SandboxPermissions,
        allowed_capabilities: Iterable[str] | None = None,
    ) -> None:
        self._sandbox = sandbox
        self._permissions = permissions
        self._allowed_capabilities = {cap.strip().lower() for cap in (allowed_capabilities or []) if cap.strip()}
        self._actions: dict[str, SystemActionSpec] = {}
        self._browser = None
        self._register_builtin_actions()

    # ------------------------------------------------------------------
    @property
    def permissions(self) -> SandboxPermissions:
        return self._permissions

    @property
    def allowed_capabilities(self) -> set[str]:
        return set(self._allowed_capabilities)

    def update_permissions(self, permissions: SandboxPermissions) -> None:
        self._permissions = permissions
        self._sandbox.update_permissions(permissions)

    def update_capabilities(self, capabilities: Iterable[str]) -> None:
        self._allowed_capabilities = {cap.strip().lower() for cap in capabilities if cap.strip()}

    # ------------------------------------------------------------------
    def register_action(self, spec: SystemActionSpec) -> None:
        self._actions[spec.name] = spec

    def actions(self) -> dict[str, SystemActionSpec]:
        return dict(self._actions)

    async def execute(self, name: str, payload: Dict[str, Any] | None = None) -> Any:
        if not name:
            raise CapabilityError("Action name is required")
        spec = self._actions.get(name)
        if spec is None:
            raise CapabilityError(f"Unknown action: {name}")
        if self._allowed_capabilities and spec.capability not in self._allowed_capabilities:
            raise CapabilityError(f"Capability not allowed by manifest: {spec.capability}")
        payload = dict(payload or {})
        for perm in spec.permissions:
            if not self._permissions.allows(perm):
                raise CapabilityError(f"Permission '{perm}' required for action '{name}'")
        return await spec.invoke(payload)

    def close(self) -> None:
        browser = self._browser
        self._browser = None
        if browser is not None:
            try:
                browser.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

    # ------------------------------------------------------------------
    def _register_builtin_actions(self) -> None:
        self.register_action(
            SystemActionSpec(
                name="system.shell.run",
                capability="shell",
                permissions=("shell_access",),
                handler=self._action_shell_run,
                summary="Execute a shell command in the sandbox and capture stdout/stderr.",
                uses_sandbox=True,
                sensitive=True,
            )
        )
        self.register_action(
            SystemActionSpec(
                name="system.files.write",
                capability="files",
                permissions=("file_access",),
                handler=self._action_files_write,
                summary="Write text to a file inside the sandbox working directory.",
                uses_sandbox=True,
                sensitive=True,
            )
        )
        self.register_action(
            SystemActionSpec(
                name="system.files.read",
                capability="files",
                permissions=("file_access",),
                handler=self._action_files_read,
                summary="Read a file from the sandbox working directory (returns text or base64).",
                uses_sandbox=True,
                sensitive=True,
            )
        )
        self.register_action(
            SystemActionSpec(
                name="system.apps.launch",
                capability="apps",
                permissions=("automation_access",),
                handler=self._action_apps_launch,
                summary="Launch a macOS application by name using the open command.",
                preview_required=True,
            )
        )
        self.register_action(
            SystemActionSpec(
                name="system.apple_script.run",
                capability="apps",
                permissions=("automation_access",),
                handler=self._action_run_applescript,
                summary="Execute a short AppleScript snippet.",
                preview_required=True,
                sensitive=True,
            )
        )
        self.register_action(
            SystemActionSpec(
                name="browser.navigate",
                capability="browser",
                permissions=("browser_access",),
                handler=self._action_browser_navigate,
                summary="Navigate Playwright-controlled browser to a URL.",
            )
        )
        self.register_action(
            SystemActionSpec(
                name="browser.click",
                capability="browser",
                permissions=("browser_access",),
                handler=self._action_browser_click,
                summary="Click an element matching a CSS selector.",
            )
        )
        self.register_action(
            SystemActionSpec(
                name="browser.fill",
                capability="browser",
                permissions=("browser_access",),
                handler=self._action_browser_fill,
                summary="Fill a form field with provided text.",
            )
        )
        self.register_action(
            SystemActionSpec(
                name="browser.extract",
                capability="browser",
                permissions=("browser_access",),
                handler=self._action_browser_extract,
                summary="Extract text or attribute content from a selector.",
            )
        )
        self.register_action(
            SystemActionSpec(
                name="browser.screenshot",
                capability="browser",
                permissions=("browser_access",),
                handler=self._action_browser_screenshot,
                summary="Capture a screenshot of the current page (full-page).",
            )
        )

    # ------------------------------------------------------------------
    # Built-in handlers
    async def _action_shell_run(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        command_raw = payload.get("command")
        args_raw = payload.get("args")
        if isinstance(command_raw, (list, tuple)):
            parts = [str(part) for part in command_raw if str(part)]
            if not parts:
                raise CapabilityError("system.shell.run requires a non-empty command")
            command = parts[0]
            extra_args = parts[1:]
            use_shell = False
        else:
            command = str(command_raw or "").strip()
            extra_args = []
            use_shell = bool(payload.get("shell", True))
        if isinstance(args_raw, (list, tuple)):
            extra_args.extend(str(part) for part in args_raw if str(part))
        if not command:
            raise CapabilityError("system.shell.run requires a command")

        env_raw = payload.get("env")
        env = {str(k): str(v) for k, v in env_raw.items()} if isinstance(env_raw, dict) else {}
        cwd_raw = payload.get("cwd")
        cwd = None
        if isinstance(cwd_raw, str):
            cwd = cwd_raw.strip() or None

        action = SandboxAction(
            target="core.system_agent:_sandbox_shell",
            args=(command, tuple(extra_args), use_shell, env, cwd),
            required_permissions=("shell_access",),
        )
        result = self._sandbox.execute(action)
        if not result.success:
            raise CapabilityError(result.error or "Shell command failed")
        value = result.value if isinstance(result.value, dict) else {}
        value.setdefault("returncode", 0)
        value.setdefault("stdout", result.stdout)
        value.setdefault("stderr", result.stderr)
        value["duration"] = result.duration
        if result.usage is not None:
            value["usage"] = result.usage
        if result.limits is not None:
            value["limits"] = result.limits
        return value

    async def _action_files_write(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = str(payload.get("path") or "").strip()
        if not path:
            raise CapabilityError("system.files.write requires a path")
        content = payload.get("content")
        if content is None:
            raise CapabilityError("system.files.write requires content")
        text = str(content)
        mode = str(payload.get("mode") or "w")
        append = bool(payload.get("append", False))
        action = SandboxAction(
            target="core.system_agent:_sandbox_write_file",
            args=(path, text, mode, append),
            required_permissions=("file_access",),
        )
        result = self._sandbox.execute(action)
        if not result.success:
            raise CapabilityError(result.error or "Failed to write file")
        value = result.value if isinstance(result.value, dict) else {}
        value.setdefault("stdout", result.stdout)
        value.setdefault("stderr", result.stderr)
        return value

    async def _action_files_read(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = str(payload.get("path") or "").strip()
        if not path:
            raise CapabilityError("system.files.read requires a path")
        binary = bool(payload.get("binary", False))
        max_bytes = int(payload.get("max_bytes") or 256 * 1024)
        action = SandboxAction(
            target="core.system_agent:_sandbox_read_file",
            args=(path, max_bytes, binary),
            required_permissions=("file_access",),
        )
        result = self._sandbox.execute(action)
        if not result.success:
            raise CapabilityError(result.error or "Failed to read file")
        value = result.value if isinstance(result.value, dict) else {}
        value.setdefault("stdout", result.stdout)
        value.setdefault("stderr", result.stderr)
        return value

    async def _action_apps_launch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if platform.system() != "Darwin":
            raise CapabilityError("system.apps.launch currently supports macOS only")
        application = str(payload.get("application") or payload.get("name") or "").strip()
        if not application:
            raise CapabilityError("Provide the application name to launch")
        raw_arguments = payload.get("arguments")
        arguments = [str(arg) for arg in raw_arguments] if isinstance(raw_arguments, (list, tuple)) else []
        cmd = ["open", "-a", application]
        cmd.extend(arguments)
        try:
            completed = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=10)
        except Exception as exc:  # pragma: no cover - subprocess errors
            raise CapabilityError(f"Failed to launch {application}: {exc}")
        return {
            "application": application,
            "returncode": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

    async def _action_run_applescript(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if platform.system() != "Darwin":
            raise CapabilityError("AppleScript automation requires macOS")
        script = str(payload.get("script") or "").strip()
        if not script:
            raise CapabilityError("Provide AppleScript text to execute")
        try:
            completed = subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                text=True,
                timeout=20,
            )
        except Exception as exc:  # pragma: no cover - subprocess errors
            raise CapabilityError(f"AppleScript failed: {exc}")
        if completed.returncode != 0:
            raise CapabilityError(completed.stderr.strip() or "AppleScript execution failed")
        return {"result": completed.stdout.strip()}

    # Browser actions --------------------------------------------------
    def _ensure_browser(self):
        if self._browser is None:
            self._browser = get_browser()
        return self._browser

    async def _action_browser_navigate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = str(payload.get("url") or "").strip()
        if not url:
            raise CapabilityError("browser.navigate requires a url")
        try:
            browser = self._ensure_browser()
            result = browser.run("navigate", url=url)
        except AgentBrowserError as exc:
            raise CapabilityError(str(exc))
        return result or {"url": url}

    async def _action_browser_click(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        selector = str(payload.get("selector") or "").strip()
        if not selector:
            raise CapabilityError("browser.click requires a selector")
        try:
            browser = self._ensure_browser()
            result = browser.run("click", selector=selector)
        except AgentBrowserError as exc:
            raise CapabilityError(str(exc))
        return result or {"status": "ok"}

    async def _action_browser_fill(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        selector = str(payload.get("selector") or "").strip()
        if not selector:
            raise CapabilityError("browser.fill requires a selector")
        text = str(payload.get("text") or "")
        try:
            browser = self._ensure_browser()
            result = browser.run("fill", selector=selector, text=text)
        except AgentBrowserError as exc:
            raise CapabilityError(str(exc))
        return result or {"status": "ok"}

    async def _action_browser_extract(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        selector = str(payload.get("selector") or "").strip()
        if not selector:
            raise CapabilityError("browser.extract requires a selector")
        attr = payload.get("attr")
        attr_value = str(attr) if isinstance(attr, str) and attr else None
        try:
            browser = self._ensure_browser()
            result = browser.run("extract", selector=selector, attr=attr_value)
        except AgentBrowserError as exc:
            raise CapabilityError(str(exc))
        return result or {"value": None}

    async def _action_browser_screenshot(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        path = str(payload.get("path") or "page.png")
        try:
            browser = self._ensure_browser()
            result = browser.run("screenshot", path=path)
        except AgentBrowserError as exc:
            raise CapabilityError(str(exc))
        return result or {"path": path}


# ----------------------------------------------------------------------
# Sandbox worker helpers. These functions must stay at module scope so the
# multiprocessing sandbox can import and execute them.

def _sandbox_shell(
    command: str,
    args: tuple[str, ...],
    use_shell: bool,
    env: Dict[str, str],
    cwd: str | None,
) -> Dict[str, Any]:
    exec_env = os.environ.copy()
    exec_env.update(env)
    if use_shell:
        completed = subprocess.run(
            command,
            shell=True,
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=exec_env,
        )
    else:
        cmd = [command, *list(args)]
        completed = subprocess.run(
            cmd,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=exec_env,
        )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def _sandbox_write_file(path: str, content: str, mode: str, append: bool) -> Dict[str, Any]:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    final_mode = mode
    if append and "a" not in final_mode:
        final_mode = final_mode.replace("w", "a") if "w" in final_mode else final_mode + "a"
    if "b" in final_mode:
        data = content.encode("utf-8")
        write_mode = final_mode
        with open(resolved, write_mode) as handle:
            handle.write(data)
        written = len(data)
    else:
        write_mode = final_mode or "w"
        with open(resolved, write_mode, encoding="utf-8") as handle:
            handle.write(content)
        written = len(content)
    return {"path": str(resolved), "bytes": written, "mode": write_mode}


def _sandbox_read_file(path: str, max_bytes: int, binary: bool) -> Dict[str, Any]:
    resolved = Path(path)
    if not resolved.is_absolute():
        resolved = Path.cwd() / resolved
    max_bytes = max(1, min(max_bytes, 2 * 1024 * 1024))  # cap at 2MB
    with open(resolved, "rb") as handle:
        data = handle.read(max_bytes + 1)
    truncated = len(data) > max_bytes
    if truncated:
        data = data[:max_bytes]
    if binary:
        payload = base64.b64encode(data).decode("ascii")
        return {"path": str(resolved), "bytes": len(data), "data": payload, "truncated": truncated, "encoding": "base64"}
    text = data.decode("utf-8", errors="replace")
    return {"path": str(resolved), "bytes": len(data), "content": text, "truncated": truncated}


__all__ = [
    "CapabilityError",
    "SystemActionSpec",
    "SystemAgent",
]
