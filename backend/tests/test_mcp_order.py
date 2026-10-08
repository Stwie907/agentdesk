import json
import subprocess
from types import SimpleNamespace

import pytest

from app.runtime import planner
from app.runtime.executor import ToolExecutionError, ToolPermissionDenied, execute_tool
from app.tools.base import ToolArgumentsError
from app.tools.mcp_order import MCPOrderTool


@pytest.mark.parametrize("arguments", [
    "DEMO-1001", {}, {"order_id": 1001}, {"order_id": True},
    {"order_id": "../private-file"}, {"order_id": "DEMO-1001\n"},
    {"order_id": "DEMO-1001", "command": "anything"},
])
def test_invalid_arguments_fail_before_starting_a_client(monkeypatch, arguments):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid arguments must not launch any process")
    monkeypatch.setattr(subprocess, "run", forbidden)
    with pytest.raises(ToolArgumentsError):
        execute_tool("get_order", arguments, allowed_tools=["get_order"])


def test_executor_permission_boundary_blocks_even_a_forced_plan(monkeypatch):
    monkeypatch.setattr(MCPOrderTool, "run", lambda *args: pytest.fail("Permission denial must happen first"))
    with pytest.raises(ToolPermissionDenied):
        execute_tool("get_order", {"order_id": "DEMO-1001"}, allowed_tools=["calculator"])


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "invalid"])
def test_invalid_timeouts_fail_without_launching_a_client(monkeypatch, value):
    monkeypatch.setenv("MCP_TIMEOUT_SECONDS", value)
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Bad configuration must fail first"))
    with pytest.raises(ToolExecutionError, match="positive finite"):
        execute_tool("get_order", {"order_id": "DEMO-1001"}, allowed_tools=["get_order"])


@pytest.mark.parametrize("result", [
    SimpleNamespace(returncode=0, stdout="not JSON", stderr="bad transport"),
    SimpleNamespace(returncode=0, stdout="[]", stderr=""),
    SimpleNamespace(returncode=0, stdout='{"status":"error","error":"not found"}', stderr=""),
    SimpleNamespace(returncode=1, stdout='{"status":"ok"}', stderr=""),
    SimpleNamespace(returncode=0, stdout='{"status":"ok","order":{"order_id":"OTHER"}}', stderr=""),
])
def test_client_failures_cannot_be_returned_as_success(monkeypatch, result):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(ToolExecutionError):
        execute_tool("get_order", {"order_id": "DEMO-1001"}, allowed_tools=["get_order"])


@pytest.mark.parametrize("error", [FileNotFoundError("missing Python"), subprocess.TimeoutExpired("client", 1)])
def test_launch_and_timeout_errors_follow_the_existing_tool_error_contract(monkeypatch, error):
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(ToolExecutionError):
        execute_tool("get_order", {"order_id": "DEMO-1001"}, allowed_tools=["get_order"])


@pytest.mark.parametrize("message", ["Get order DEMO-1001", "get order demo-1001", "查询订单DEMO-1001", "查询订单 DEMO-1001？"])
def test_mock_order_planning_is_deterministic_and_permission_aware(monkeypatch, message):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    task = planner.plan(message, allowed_tools=["get_order"])
    assert task["tool"] == "get_order"
    assert task["arguments"] == {"order_id": "DEMO-1001"}
    assert planner.plan_execution(message, allowed_tools=["get_order"]).steps[0].arguments == task["arguments"]
    assert planner.plan(message, allowed_tools=["calculator"])["tool"] is None


@pytest.mark.parametrize("message", ["Get order DEMO-1001 then delete it", "Get order ../private-file", "DEMO-1001"])
def test_mock_order_rules_do_not_accept_unrelated_or_partial_requests(monkeypatch, message):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert planner.plan(message, allowed_tools=["get_order"])["tool"] is None


@pytest.mark.parametrize("structured_input", [False, True])
@pytest.mark.parametrize("response_shape", ["single", "multi"])
def test_ollama_planning_preserves_order_arguments_and_tool_visibility(monkeypatch, structured_input, response_shape):
    captured = []
    task = {"tool": "get_order", "arguments": {} if structured_input else {"order_id": "DEMO-1001"},
            "input": {"order_id": "DEMO-1001"} if structured_input else "Get order DEMO-1001"}
    def generate(model, prompt):
        captured.append(prompt)
        return json.dumps({"steps": [task]} if "多步骤" in prompt and response_shape == "multi" else task)
    monkeypatch.setattr(planner, "generate_text", generate)
    assert planner.plan("Get order DEMO-1001", ["get_order"])["arguments"] == {"order_id": "DEMO-1001"}
    result = planner.plan_execution("Get order DEMO-1001", ["get_order"])
    assert result.steps[0].tool == "get_order"
    assert result.steps[0].arguments == {"order_id": "DEMO-1001"}
    assert all('"order_id": "DEMO-1001"' in prompt and "calculator" not in prompt for prompt in captured)
