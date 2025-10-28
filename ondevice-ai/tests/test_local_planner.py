import json

import pytest

from core.local_planner import LocalPlannerModel


@pytest.fixture(scope="module")
def planner() -> LocalPlannerModel:
    return LocalPlannerModel()


def _payload(action):
    return json.loads(action["payload"]) if action.get("payload") else {}


def test_shell_plan(planner: LocalPlannerModel) -> None:
    plan = planner.plan("run `ls -la` in project root")
    assert plan and plan[0]["name"] == "system.shell.run"
    payload = _payload(plan[0])
    assert payload["command"] == "ls -la"
    assert payload["shell"] is True


def test_file_write_plan(planner: LocalPlannerModel) -> None:
    plan = planner.plan("write meeting notes to /tmp/notes.txt")
    assert plan[0]["name"] == "system.files.write"
    write_payload = _payload(plan[0])
    assert write_payload["path"].endswith("notes.txt")
    assert "meeting notes" in write_payload["content"]
    assert plan[1]["name"] == "system.files.read"


def test_browser_plan(planner: LocalPlannerModel) -> None:
    plan = planner.plan("open https://example.com and capture it")
    assert plan[0]["name"] == "browser.navigate"
    nav_payload = _payload(plan[0])
    assert nav_payload["url"].startswith("https://example.com")


def test_app_launch_plan(planner: LocalPlannerModel) -> None:
    plan = planner.plan("launch Safari")
    assert plan[0]["name"] == "system.apps.launch"
    payload = _payload(plan[0])
    assert payload["application"].startswith("Safari")


def test_applescript_plan(planner: LocalPlannerModel) -> None:
    plan = planner.plan("run an applescript to toggle do not disturb")
    assert plan[0]["name"] == "system.apple_script.run"
    payload = _payload(plan[0])
    assert "tell application" in payload["script"].lower() or "display dialog" in payload["script"].lower()


def test_embed_dimension(planner: LocalPlannerModel) -> None:
    vectors = planner.embed(["hello world"])
    assert len(vectors) == 1
    assert len(vectors[0]) == planner._VECTOR_SIZE