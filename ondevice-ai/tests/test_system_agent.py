import asyncio
import os
from pathlib import Path
from typing import cast

import pytest

from core import sandbox as sandbox_module
from core.sandbox import SandboxAction, SandboxHarness, SandboxPermissions, SandboxResult
from core.system_agent import CapabilityError, SystemAgent


class InlineSandboxHarness:
    def __init__(self, workdir: Path, permissions: SandboxPermissions) -> None:
        self.workdir = workdir
        self.permissions = permissions

    def execute(self, action: SandboxAction) -> SandboxResult:
        denied = [scope for scope in action.required_permissions if not self.permissions.allows(scope)]
        if denied:
            raise PermissionError(f"Permissions denied: {', '.join(denied)}")

        cwd = os.getcwd()
        try:
            os.chdir(self.workdir)
            result = sandbox_module._invoke_target(action.target, action.args, action.kwargs)
        finally:
            os.chdir(cwd)

        return SandboxResult(
            success=True,
            value=result,
            stdout="",
            stderr="",
            duration=0.0,
            timed_out=False,
        )

    def update_permissions(self, permissions: SandboxPermissions) -> None:
        self.permissions = permissions


def _make_agent(
    workdir: Path,
    *,
    permissions: SandboxPermissions,
    capabilities: set[str] | None = None,
) -> SystemAgent:
    harness = InlineSandboxHarness(workdir, permissions)
    return SystemAgent(
        sandbox=cast(SandboxHarness, harness),
        permissions=permissions,
        allowed_capabilities=capabilities or permissions_as_capabilities(permissions),
    )


def permissions_as_capabilities(perms: SandboxPermissions) -> set[str]:
    mapping = {
        "files": perms.file_access,
        "shell": perms.shell_access,
        "browser": perms.browser_access,
        "apps": perms.automation_access,
    }
    return {name for name, enabled in mapping.items() if enabled}


def test_system_shell_run_success(tmp_path: Path) -> None:
    permissions = SandboxPermissions(
        file_access=True,
        network_access=False,
        calendar_access=False,
        mail_access=False,
        browser_access=False,
        automation_access=False,
        shell_access=True,
    )
    agent = _make_agent(tmp_path, permissions=permissions, capabilities={"shell"})

    result = asyncio.run(agent.execute("system.shell.run", {"command": "echo hello world", "shell": True}))
    assert result["returncode"] == 0
    assert "hello world" in result["stdout"]


def test_system_files_write_and_read(tmp_path: Path) -> None:
    permissions = SandboxPermissions(
        file_access=True,
        network_access=False,
        calendar_access=False,
        mail_access=False,
        browser_access=False,
        automation_access=False,
        shell_access=True,
    )
    agent = _make_agent(tmp_path, permissions=permissions, capabilities={"files", "shell"})

    asyncio.run(
        agent.execute(
            "system.files.write",
            {"path": "notes.txt", "content": "automation ftw"},
        )
    )
    read_result = asyncio.run(agent.execute("system.files.read", {"path": "notes.txt"}))
    assert "automation ftw" in read_result.get("content", "")


def test_system_shell_respects_permissions(tmp_path: Path) -> None:
    permissions = SandboxPermissions(
        file_access=False,
        network_access=False,
        calendar_access=False,
        mail_access=False,
        browser_access=False,
        automation_access=False,
        shell_access=False,
    )
    agent = _make_agent(tmp_path, permissions=permissions, capabilities={"shell"})

    with pytest.raises(CapabilityError):
        asyncio.run(agent.execute("system.shell.run", {"command": "echo should fail"}))


def test_capability_gate(tmp_path: Path) -> None:
    permissions = SandboxPermissions(
        file_access=True,
        network_access=False,
        calendar_access=False,
        mail_access=False,
        browser_access=False,
        automation_access=False,
        shell_access=True,
    )
    agent = _make_agent(tmp_path, permissions=permissions, capabilities={"files"})
    with pytest.raises(CapabilityError):
        asyncio.run(agent.execute("system.shell.run", {"command": "echo"}))

    agent.update_capabilities({"files", "shell"})
    result = asyncio.run(agent.execute("system.shell.run", {"command": "echo ok"}))
    assert result["returncode"] == 0
