"""Verify real ticket writes, idempotent replay, and permission boundaries."""

import json
import sqlite3

import pytest

from app.models.agent import Agent
from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.services import agent_runner
from app.tools.mcp_ticket import MCPTicketTool

from test_mcp_runtime_api import demo_api, sdk_python


@pytest.fixture
def ticket_path(tmp_path, monkeypatch):
    path = tmp_path / "tickets.db"
    monkeypatch.setenv("MCP_TICKET_DB", str(path))
    return path


def stored_count(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("SELECT COUNT(*) FROM demo_tickets").fetchone()[0]


@pytest.mark.parametrize("message,problem", [("Create ticket Demo parcel is delayed.", "Demo parcel is delayed."),
                                            ("创建工单示例包裹延误。", "示例包裹延误。")])
def test_ticket_task_returns_traced_and_snapshotted_persistent_data(demo_api, sdk_python, ticket_path, message, problem):
    client, ids, _ = demo_api
    reply = client.post(f'/agents/{ids["ticket_agent_id"]}/chat', json={"message": message}).json()
    assert reply["status"] == "completed"
    ticket = json.loads(reply["response"])
    assert ticket["problem"] == problem and ticket["source"] == "demo_ticket_store" and ticket["status"] == "open"
    assert ticket["ticket_id"].startswith("DEMO-TICKET-") and stored_count(ticket_path) == 1
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert [event["event"] for event in trace] == ["plan_started", "step_started", "step_completed", "plan_completed"]
    assert trace[1]["tool"] == "create_ticket" and "transport=mcp_stdio" in trace[1]["message"]
    assert "result=" + reply["response"] in trace[2]["message"]
    snapshot = client.get(f'/executions/{reply["execution_id"]}/snapshot').json()
    assert snapshot["output_snapshot"] == reply["response"]
    assert json.loads(snapshot["plan_snapshot"])["steps"][0]["arguments"] == {"problem": problem}


def test_repeated_tasks_and_real_replay_do_not_duplicate_tickets(demo_api, sdk_python, ticket_path, monkeypatch):
    client, ids, _ = demo_api
    endpoint = f'/agents/{ids["ticket_agent_id"]}/chat'
    source = client.post(endpoint, json={"message": "Create ticket Demo problem"}).json()
    repeated = client.post(endpoint, json={"message": "Create ticket   Demo problem  "}).json()
    assert source["status"] == repeated["status"] == "completed"
    assert repeated["response"] == source["response"]
    monkeypatch.setattr(agent_runner, "plan_execution", lambda *args, **kwargs: pytest.fail("Replay must not plan again"))
    replay = client.post(f'/executions/{source["execution_id"]}/replay', json={}).json()
    assert replay["status"] == "completed" and replay["output"] == source["response"]
    assert replay["replay_of_execution_id"] == source["execution_id"]
    trace = client.get(f'/executions/{replay["id"]}/trace').json()
    assert all(event["execution_id"] == replay["id"] for event in trace)
    assert "result=" + replay["output"] in trace[2]["message"]
    assert client.get(f'/executions/{replay["id"]}/snapshot').json()["output_snapshot"] == replay["output"]
    assert client.get(f'/executions/{source["execution_id"]}/replays').json()[0]["id"] == replay["id"]
    assert stored_count(ticket_path) == 1


def test_revoked_write_permission_blocks_replay_before_mcp(demo_api, sdk_python, ticket_path, monkeypatch):
    client, ids, sessions = demo_api
    source = client.post(f'/agents/{ids["ticket_agent_id"]}/chat', json={"message": "Create ticket Demo problem"}).json()
    with sessions() as db:
        db.get(Agent, ids["ticket_agent_id"]).allowed_tools = "[]"
        db.commit()
    monkeypatch.setattr(MCPTicketTool, "run", lambda *args: pytest.fail("Revoked permission must prevent writes"))
    failed = client.post(f'/executions/{source["execution_id"]}/replay', json={})
    assert failed.status_code == 500 and failed.json()["detail"]["failure_type"] == "tool_permission_denied"
    replay = client.get(f'/executions/{source["execution_id"]}/replays').json()[0]
    assert replay["status"] == "failed" and replay["failure_type"] == "tool_permission_denied"
    assert stored_count(ticket_path) == 1


def test_read_only_agents_cannot_write_even_if_a_plan_is_forced(demo_api, ticket_path, monkeypatch):
    client, ids, _ = demo_api
    monkeypatch.setattr(MCPTicketTool, "run", lambda *args: pytest.fail("Permission must be checked before writing"))
    endpoint = f'/agents/{ids["tracking_agent_id"]}/chat'
    reply = client.post(endpoint, json={"message": "Create ticket Demo problem"}).json()
    assert reply["status"] == "completed" and reply["response"].startswith("[MOCK]")
    monkeypatch.setattr(agent_runner, "plan_execution", lambda *args, **kwargs: ExecutionPlan(
        steps=[ExecutionStep(tool="create_ticket", arguments={"problem": "Demo problem"}, input="forced")]))
    forced = client.post(endpoint, json={"message": "forced"}).json()
    assert forced["status"] == "failed"
    assert client.get(f'/executions/{forced["execution_id"]}').json()["failure_type"] == "tool_permission_denied"
    assert not ticket_path.exists()


def test_database_write_failure_and_failed_replay_are_recorded(demo_api, sdk_python, tmp_path, monkeypatch):
    monkeypatch.setenv("MCP_TICKET_DB", str(tmp_path))
    client, ids, _ = demo_api
    reply = client.post(f'/agents/{ids["ticket_agent_id"]}/chat', json={"message": "Create ticket Demo problem"}).json()
    assert reply["status"] == "failed" and "Cannot create a demo ticket" in reply["response"]
    execution = client.get(f'/executions/{reply["execution_id"]}').json()
    assert execution["failure_type"] == "tool_execution_error" and execution["retry_count"] == 0
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert [row["event"] for row in trace] == ["plan_started", "step_started", "step_failed", "plan_failed"]
    failed = client.post(f'/executions/{reply["execution_id"]}/replay', json={})
    assert failed.status_code == 500 and failed.json()["detail"]["failure_type"] == "tool_execution_error"
    replay = client.get(f'/executions/{reply["execution_id"]}/replays').json()[0]
    assert replay["status"] == "failed" and replay["output"] is None
