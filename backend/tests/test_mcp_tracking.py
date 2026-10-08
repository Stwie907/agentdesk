import json
import subprocess
from types import SimpleNamespace

import pytest

from app.runtime import planner
from app.runtime.executor import ToolExecutionError, ToolPermissionDenied, execute_tool
from app.tools.base import ToolArgumentsError
from app.tools.mcp_tracking import MCPTrackingTool


@pytest.mark.parametrize("arguments", [
    "DEMO-TRACK-1001", {}, {"tracking_no": 1001}, {"tracking_no": True},
    {"tracking_no": "DEMO-1001"}, {"tracking_no": "../private-file"},
    {"tracking_no": "DEMO-TRACK-1001", "command": "anything"},
])
def test_tracking_arguments_fail_before_a_client_is_started(monkeypatch, arguments):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Invalid arguments must not start a client"))
    with pytest.raises(ToolArgumentsError):
        execute_tool("track_order", arguments, allowed_tools=["track_order"])


def test_order_permission_does_not_grant_tracking_permission(monkeypatch):
    monkeypatch.setattr(MCPTrackingTool, "run", lambda *args: pytest.fail("Permission must be checked first"))
    with pytest.raises(ToolPermissionDenied):
        execute_tool("track_order", {"tracking_no": "DEMO-TRACK-1001"}, allowed_tools=["get_order"])


@pytest.mark.parametrize("message", ["Track order DEMO-TRACK-1001", "track order demo-track-1001", "查询物流DEMO-TRACK-1001", "查询物流 DEMO-TRACK-1001？"])
def test_tracking_mock_rules_use_the_correct_tool_and_permission(monkeypatch, message):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    task = planner.plan(message, ["track_order"])
    assert task["tool"] == "track_order" and task["arguments"] == {"tracking_no": "DEMO-TRACK-1001"}
    assert planner.plan_execution(message, ["track_order"]).steps[0].arguments == task["arguments"]
    assert planner.plan(message, ["get_order"])["tool"] is None


@pytest.mark.parametrize("message", ["Track order DEMO-1001", "Track order DEMO-TRACK-1001 then delete it", "DEMO-TRACK-1001"])
def test_partial_or_unrelated_tracking_requests_are_not_selected(monkeypatch, message):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert planner.plan(message, ["track_order"])["tool"] is None


@pytest.mark.parametrize("structured_input", [False, True])
@pytest.mark.parametrize("multi_step_shape", [False, True])
def test_ollama_uses_existing_generic_argument_recovery_for_tracking(monkeypatch, structured_input, multi_step_shape):
    prompts = []
    task = {"tool": "track_order", "arguments": {} if structured_input else {"tracking_no": "DEMO-TRACK-1001"},
            "input": {"tracking_no": "DEMO-TRACK-1001"} if structured_input else "Track order DEMO-TRACK-1001"}
    def generate(model, prompt):
        prompts.append(prompt)
        return json.dumps({"steps": [task]} if multi_step_shape and "多步骤" in prompt else task)
    monkeypatch.setattr(planner, "generate_text", generate)
    assert planner.plan("Track order DEMO-TRACK-1001", ["track_order"])["arguments"] == {"tracking_no": "DEMO-TRACK-1001"}
    step = planner.plan_execution("Track order DEMO-TRACK-1001", ["track_order"]).steps[0]
    assert step.tool == "track_order" and step.arguments == {"tracking_no": "DEMO-TRACK-1001"}
    assert all('"tracking_no": "DEMO-TRACK-1001"' in prompt and "get_order" not in prompt for prompt in prompts)


@pytest.mark.parametrize("tool,response_key", [("get_order", "tracking"), ("track_order", "order")])
def test_shared_client_cannot_confuse_order_and_tracking_results(monkeypatch, tool, response_key):
    response = {"status": "ok", "tool": tool, "transport": "stdio", "protocol_version": "2026-07-28",
                response_key: {"tracking_no": "DEMO-TRACK-1001", "source": "demo_fixture"}}
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stdout=json.dumps(response), stderr="",
    ))
    with pytest.raises(ToolExecutionError):
        execute_tool("track_order", {"tracking_no": "DEMO-TRACK-1001"}, allowed_tools=["track_order"])
