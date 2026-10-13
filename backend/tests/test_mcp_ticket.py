import json
import subprocess
from types import SimpleNamespace

import pytest

from app.runtime import planner
from app.runtime.executor import ToolExecutionError, ToolPermissionDenied, execute_tool
from app.tools.base import ToolArgumentsError
from app.tools.mcp_ticket import MCPTicketTool


@pytest.mark.parametrize("arguments", ["Demo problem", {}, {"problem": 1}, {"problem": True},
    {"problem": ""}, {"problem": " \n\t"}, {"problem": "x" * 2001}, {"problem": "Demo", "command": "x"}])
def test_invalid_ticket_arguments_never_start_a_client(monkeypatch, arguments):
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: pytest.fail("Invalid problems must not start MCP"))
    with pytest.raises(ToolArgumentsError):
        execute_tool("create_ticket", arguments, allowed_tools=["create_ticket"])


@pytest.mark.parametrize("permissions", [[], ["get_order"], ["track_order"]])
def test_read_only_permissions_do_not_grant_ticket_write_permission(monkeypatch, permissions):
    monkeypatch.setattr(MCPTicketTool, "run", lambda *args: pytest.fail("Permission must be checked before writing"))
    with pytest.raises(ToolPermissionDenied):
        execute_tool("create_ticket", {"problem": "Demo problem"}, allowed_tools=permissions)


@pytest.mark.parametrize("message", ["Create ticket Demo problem", "create ticket Demo problem", "创建工单Demo problem", "创建工单 Demo problem"])
def test_fixed_ticket_commands_require_the_write_permission(monkeypatch, message):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    task = planner.plan(message, ["create_ticket"])
    assert task["tool"] == "create_ticket" and task["arguments"] == {"problem": "Demo problem"}
    assert planner.plan_execution(message, ["create_ticket"]).steps[0].arguments == task["arguments"]
    assert planner.plan(message, ["track_order", "get_order"])["tool"] is None


@pytest.mark.parametrize("message", ["Create ticket", "Create ticket   ", "创建工单", "Create ticket " + "x" * 2001])
def test_empty_or_oversized_mock_ticket_requests_are_not_selected(monkeypatch, message):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert planner.plan(message, ["create_ticket"])["tool"] is None


@pytest.mark.parametrize("structured_input", [False, True])
@pytest.mark.parametrize("multi_step", [False, True])
def test_ticket_uses_the_existing_generic_planner_contract(monkeypatch, structured_input, multi_step):
    task = {"tool": "create_ticket", "arguments": {} if structured_input else {"problem": "Demo parcel is delayed."},
            "input": {"problem": "Demo parcel is delayed."} if structured_input else "Create ticket Demo parcel is delayed."}
    monkeypatch.setattr(planner, "generate_text", lambda model, prompt: json.dumps(
        {"steps": [task]} if multi_step and "多步骤" in prompt else task))
    assert planner.plan("Create ticket Demo parcel is delayed.", ["create_ticket"])["arguments"] == {"problem": "Demo parcel is delayed."}
    assert planner.plan_execution("Create ticket Demo parcel is delayed.", ["create_ticket"]).steps[0].arguments == {"problem": "Demo parcel is delayed."}


def test_ticket_adapter_passes_normalized_text_over_stdin_and_keeps_the_direct_result(monkeypatch):
    ticket = {"problem": "Demo problem", "source": "demo_ticket_store", "ticket_id": "DEMO-TICKET-" + "a" * 32,
              "status": "open", "created_at": "2026-10-08T08:00:00Z"}
    def run(command, **kwargs):
        assert "create_ticket" in command and "Demo problem" not in command
        assert json.loads(kwargs["input"]) == {"problem": "Demo problem"}
        assert not kwargs.get("shell")
        return SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
            "status": "ok", "tool": "create_ticket", "transport": "stdio", "protocol_version": "2026-07-28", "ticket": ticket}))
    monkeypatch.setattr(subprocess, "run", run)
    assert json.loads(execute_tool("create_ticket", {"problem": "  Demo problem  "}, allowed_tools=["create_ticket"])) == ticket
    assert MCPTicketTool.return_direct is True


@pytest.mark.parametrize("field,value", [("source", "demo_fixture"), ("problem", "Different problem")])
def test_ticket_adapter_rejects_an_unrelated_or_incompatible_record(monkeypatch, field, value):
    ticket = {"source": "demo_ticket_store", "problem": "Demo problem"}
    ticket[field] = value
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: SimpleNamespace(
        returncode=0, stderr="", stdout=json.dumps({"status": "ok", "tool": "create_ticket", "transport": "stdio",
                                                   "protocol_version": "2026-07-28", "ticket": ticket})))
    with pytest.raises(ToolExecutionError):
        execute_tool("create_ticket", {"problem": "Demo problem"}, allowed_tools=["create_ticket"])
