from __future__ import annotations

import sys

import pytest

from core.sandbox import SandboxAction, SandboxConfig, SandboxHarness, SandboxPermissions


def test_sandbox_allows_basic_action(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path, wall_time_seconds=2.0)
    permissions = SandboxPermissions()
    harness = SandboxHarness(config=config, permissions=permissions)

    action = SandboxAction(target="tests.sandbox_targets:add_numbers", args=(2, 3))
    result = harness.execute(action)

    assert result.success is True
    assert result.value == 5
    assert result.timed_out is False


def test_sandbox_requires_permission(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path)
    permissions = SandboxPermissions(file_access=False)
    harness = SandboxHarness(config=config, permissions=permissions)

    action = SandboxAction(
        target="tests.sandbox_targets:write_file",
        args=("note.txt", "hello"),
        required_permissions=("file_access",),
    )

    with pytest.raises(PermissionError):
        harness.execute(action)


def test_sandbox_blocks_network(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path, wall_time_seconds=2.0)
    permissions = SandboxPermissions(network_access=False)
    harness = SandboxHarness(config=config, permissions=permissions)

    action = SandboxAction(target="tests.sandbox_targets:attempt_socket_connection")
    result = harness.execute(action)

    assert result.success is False
    assert "Network access is disabled" in (result.error or "")


def test_sandbox_allows_file_access_in_workdir(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path)
    permissions = SandboxPermissions(file_access=True)
    harness = SandboxHarness(config=config, permissions=permissions)

    action = SandboxAction(
        target="tests.sandbox_targets:write_file",
        args=("document.txt", "data"),
        required_permissions=("file_access",),
    )
    result = harness.execute(action)

    assert result.success is True
    assert (tmp_path / "document.txt").read_text() == "data"
    assert result.value == "data"


def test_sandbox_times_out(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path, wall_time_seconds=0.2)
    permissions = SandboxPermissions()
    harness = SandboxHarness(config=config, permissions=permissions)

    action = SandboxAction(target="tests.sandbox_targets:slow_operation", args=(1.0,))
    result = harness.execute(action)

    assert result.success is False
    assert result.timed_out is True
    assert result.error == "Timed out waiting for sandbox action"


def test_sandbox_result_includes_limits_and_usage(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path, wall_time_seconds=2.0, collect_usage=True)
    permissions = SandboxPermissions()
    harness = SandboxHarness(config=config, permissions=permissions)

    action = SandboxAction(target="tests.sandbox_targets:add_numbers", args=(4, 5))
    result = harness.execute(action)

    assert result.success is True
    assert isinstance(result.limits, dict)
    assert "cpu_time" in result.limits
    assert "memory" in result.limits
    assert isinstance(result.usage, dict)
    assert "user_time" in result.usage


def test_sandbox_usage_collection_toggle(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path, wall_time_seconds=2.0, collect_usage=False)
    permissions = SandboxPermissions()
    harness = SandboxHarness(config=config, permissions=permissions)

    action = SandboxAction(target="tests.sandbox_targets:add_numbers", args=(1, 2))
    result = harness.execute(action)

    assert result.success is True
    assert result.usage is None


@pytest.mark.skipif(sys.platform != "darwin", reason="mac-specific defaults")
def test_sandbox_mac_defaults(tmp_path) -> None:
    cfg = SandboxConfig.mac_defaults(working_dir=tmp_path)
    assert cfg.cpu_time_seconds == 10
    assert cfg.wall_time_seconds == 15.0
    assert cfg.memory_bytes == 1_024 * 1024 * 1024
    assert cfg.max_open_files == 512
    assert cfg.max_processes == 128
    assert cfg.max_output_bytes == 256 * 1024 * 1024
    assert cfg.idle_priority is True
    assert cfg.collect_usage is True
    assert cfg.working_dir == tmp_path.resolve()


def test_update_permissions_refreshes_network(tmp_path) -> None:
    config = SandboxConfig(working_dir=tmp_path, wall_time_seconds=1.0, allow_network=False)
    permissions = SandboxPermissions(network_access=False)
    harness = SandboxHarness(config=config, permissions=permissions)

    updated = SandboxPermissions(network_access=True)
    harness.update_permissions(updated)

    assert harness.permissions.network_access is True
    assert harness.config.allow_network is True
