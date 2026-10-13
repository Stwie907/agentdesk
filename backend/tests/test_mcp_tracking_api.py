"""Real shipment subprocess calls through task submission and replay."""

import json

import pytest

from app.models.agent import Agent
from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.services import agent_runner
from app.tools.mcp_tracking import MCPTrackingTool

# Reuse the isolated API/SDK fixtures from the order integration suite.
from test_mcp_runtime_api import demo_api, sdk_python


@pytest.mark.parametrize("message,tracking_no,status,event_count", [
    ("Track order DEMO-TRACK-1001", "DEMO-TRACK-1001", "in_transit", 3),
    ("查询物流DEMO-TRACK-1002", "DEMO-TRACK-1002", "label_created", 1),
])
def test_tracking_task_persists_json_trace_and_snapshot(demo_api, sdk_python, message, tracking_no, status, event_count):
    client, ids, _ = demo_api
    response = client.post(f'/agents/{ids["tracking_agent_id"]}/chat', json={"message": message})
    assert response.status_code == 200
    reply = response.json()
    assert reply["status"] == "completed"
    shipment = json.loads(reply["response"])
    assert (shipment["tracking_no"], shipment["status"], shipment["source"]) == (tracking_no, status, "demo_fixture")
    assert len(shipment["events"]) == event_count
    assert shipment["events"][-1]["status"] == shipment["status"]
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert [event["event"] for event in trace] == ["plan_started", "step_started", "step_completed", "plan_completed"]
    assert trace[1]["tool"] == "track_order" and f'"tracking_no": "{tracking_no}"' in trace[1]["message"]
    assert "result=" + reply["response"] in trace[2]["message"]
    snapshot = client.get(f'/executions/{reply["execution_id"]}/snapshot').json()
    assert snapshot["output_snapshot"] == reply["response"]
    assert json.loads(snapshot["plan_snapshot"])["steps"][0]["arguments"] == {"tracking_no": tracking_no}


def test_tracking_replay_uses_saved_plan_and_preserves_history(demo_api, sdk_python, monkeypatch):
    client, ids, _ = demo_api
    source = client.post(f'/agents/{ids["tracking_agent_id"]}/chat', json={"message": "Track order DEMO-TRACK-1001"}).json()
    monkeypatch.setattr(agent_runner, "plan_execution", lambda *args, **kwargs: pytest.fail("Replay must not plan again"))
    response = client.post(f'/executions/{source["execution_id"]}/replay', json={})
    assert response.status_code == 200
    replay = response.json()
    assert replay["status"] == "completed" and replay["output"] == source["response"]
    assert replay["replay_of_execution_id"] == source["execution_id"]
    trace = client.get(f'/executions/{replay["id"]}/trace').json()
    assert all(event["execution_id"] == replay["id"] for event in trace)
    assert '"tracking_no": "DEMO-TRACK-1001"' in trace[1]["message"]
    assert "result=" + source["response"] in trace[2]["message"]
    snapshot = client.get(f'/executions/{replay["id"]}/snapshot').json()
    assert snapshot["output_snapshot"] == source["response"]
    history = client.get(f'/executions/{source["execution_id"]}/replays').json()
    assert [row["id"] for row in history] == [replay["id"]]


def test_unknown_tracking_failure_and_failed_replay_are_persisted(demo_api, sdk_python):
    client, ids, _ = demo_api
    reply = client.post(f'/agents/{ids["tracking_agent_id"]}/chat', json={"message": "Track order DEMO-TRACK-9999"}).json()
    assert reply["status"] == "failed" and "not found" in reply["response"]
    record = client.get(f'/executions/{reply["execution_id"]}').json()
    assert record["failure_type"] == "tool_execution_error" and record["retry_count"] == 0
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert [event["event"] for event in trace] == ["plan_started", "step_started", "step_failed", "plan_failed"]
    assert "not found" in trace[2]["error"]
    response = client.post(f'/executions/{reply["execution_id"]}/replay', json={})
    assert response.status_code == 500 and response.json()["detail"]["failure_type"] == "tool_execution_error"
    replay = client.get(f'/executions/{reply["execution_id"]}/replays').json()[0]
    assert replay["status"] == "failed" and replay["output"] is None
    assert client.get(f'/executions/{replay["id"]}/snapshot').status_code == 200


def test_tracking_replay_honors_revoked_permission(demo_api, sdk_python, monkeypatch):
    client, ids, sessions = demo_api
    source = client.post(f'/agents/{ids["tracking_agent_id"]}/chat', json={"message": "Track order DEMO-TRACK-1001"}).json()
    with sessions() as db:
        db.get(Agent, ids["tracking_agent_id"]).allowed_tools = "[]"
        db.commit()
    monkeypatch.setattr(MCPTrackingTool, "run", lambda *args: pytest.fail("Revoked permissions must block the client"))
    response = client.post(f'/executions/{source["execution_id"]}/replay', json={})
    assert response.status_code == 500 and response.json()["detail"]["failure_type"] == "tool_permission_denied"
    replay = client.get(f'/executions/{source["execution_id"]}/replays').json()[0]
    assert replay["status"] == "failed" and replay["failure_type"] == "tool_permission_denied"


def test_order_agent_cannot_run_a_tracking_tool_even_with_a_forced_plan(demo_api, monkeypatch):
    client, ids, _ = demo_api
    monkeypatch.setattr(MCPTrackingTool, "run", lambda *args: pytest.fail("Tracking must not run without permission"))
    reply = client.post(f'/agents/{ids["mcp_agent_id"]}/chat', json={"message": "Track order DEMO-TRACK-1001"}).json()
    assert reply["status"] == "completed" and reply["response"].startswith("[MOCK]")
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert all(event["tool"] is None for event in trace)
    monkeypatch.setattr(agent_runner, "plan_execution", lambda *args, **kwargs: ExecutionPlan(
        steps=[ExecutionStep(tool="track_order", arguments={"tracking_no": "DEMO-TRACK-1001"}, input="forced")],
    ))
    reply = client.post(f'/agents/{ids["mcp_agent_id"]}/chat', json={"message": "forced"}).json()
    assert reply["status"] == "failed"
    record = client.get(f'/executions/{reply["execution_id"]}').json()
    assert record["failure_type"] == "tool_permission_denied"
