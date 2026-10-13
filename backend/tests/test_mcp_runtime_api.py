"""Exercise real MCP subprocesses through the existing chat and replay APIs."""

import json
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient
import pytest
import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.agent import Agent
from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.seed_demo import seed_demo
from app.services import agent_runner
from app.tools.mcp_order import MCPOrderTool, mcp_python
from app.workers import execution_worker


@pytest.fixture
def sdk_python():
    executable = mcp_python()
    if executable == sys.executable and not os.getenv("MCP_PYTHON"):
        pytest.skip("Install mcp-server/.venv or set MCP_PYTHON for real MCP integration tests")
    assert Path(executable).is_file(), "MCP_PYTHON must point to an installed isolated MCP environment"
    return executable


@pytest.fixture
def demo_api(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine)
    with sessions() as db:
        ids = seed_demo(db)
    def override_db():
        with sessions() as db:
            yield db
    previous = app.dependency_overrides.get(get_db)
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(execution_worker, "SessionLocal", sessions)
    monkeypatch.setattr(agent_runner, "SessionLocal", sessions)
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *args, **kwargs: pytest.fail("Mock must make no model requests"))
    try:
        with TestClient(app) as client:
            yield client, ids, sessions
    finally:
        if previous is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous
        engine.dispose()


@pytest.mark.parametrize("order_id,status", [("DEMO-1001", "shipped"), ("DEMO-1002", "processing")])
def test_real_mcp_order_is_returned_traced_and_snapshotted(demo_api, sdk_python, order_id, status):
    client, ids, _ = demo_api
    response = client.post(f'/agents/{ids["mcp_agent_id"]}/chat', json={"message": f"Get order {order_id}"})
    assert response.status_code == 200
    reply = response.json()
    assert reply["status"] == "completed"
    order = json.loads(reply["response"])
    assert (order["order_id"], order["status"], order["source"]) == (order_id, status, "demo_fixture")
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert [event["event"] for event in trace] == ["plan_started", "step_started", "step_completed", "plan_completed"]
    assert f'"order_id": "{order_id}"' in trace[1]["message"]
    assert "transport=mcp_stdio" in trace[1]["message"]
    assert "result=" + reply["response"] in trace[2]["message"]
    snapshot = client.get(f'/executions/{reply["execution_id"]}/snapshot').json()
    assert snapshot["output_snapshot"] == reply["response"]
    assert json.loads(snapshot["plan_snapshot"])["steps"][0]["arguments"] == {"order_id": order_id}


def test_real_mcp_replay_uses_stored_plan_and_its_own_trace(demo_api, sdk_python, monkeypatch):
    client, ids, _ = demo_api
    source = client.post(f'/agents/{ids["mcp_agent_id"]}/chat', json={"message": "Get order DEMO-1001"}).json()
    monkeypatch.setattr(agent_runner, "plan_execution", lambda *args, **kwargs: pytest.fail("Replay must not plan again"))
    response = client.post(f'/executions/{source["execution_id"]}/replay', json={})
    assert response.status_code == 200
    replay = response.json()
    assert replay["status"] == "completed" and replay["output"] == source["response"]
    assert replay["replay_of_execution_id"] == source["execution_id"]
    trace = client.get(f'/executions/{replay["id"]}/trace').json()
    assert all(event["execution_id"] == replay["id"] for event in trace)
    assert "arguments=" in trace[1]["message"] and "result=" + replay["output"] in trace[2]["message"]
    snapshot = client.get(f'/executions/{replay["id"]}/snapshot').json()
    assert snapshot["output_snapshot"] == source["response"]
    history = client.get(f'/executions/{source["execution_id"]}/replays').json()
    assert [row["id"] for row in history] == [replay["id"]]


def test_unknown_order_persists_failure_and_failed_replay(demo_api, sdk_python):
    client, ids, _ = demo_api
    reply = client.post(f'/agents/{ids["mcp_agent_id"]}/chat', json={"message": "Get order DEMO-9999"}).json()
    assert reply["status"] == "failed" and "not found" in reply["response"]
    record = client.get(f'/executions/{reply["execution_id"]}').json()
    assert record["failure_type"] == "tool_execution_error" and record["retry_count"] == 0
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert [event["event"] for event in trace] == ["plan_started", "step_started", "step_failed", "plan_failed"]
    assert "not found" in trace[2]["error"]
    response = client.post(f'/executions/{reply["execution_id"]}/replay', json={})
    assert response.status_code == 500
    assert response.json()["detail"]["failure_type"] == "tool_execution_error"
    failed_replay = client.get(f'/executions/{reply["execution_id"]}/replays').json()[0]
    assert failed_replay["status"] == "failed" and failed_replay["output"] is None
    assert client.get(f'/executions/{failed_replay["id"]}/snapshot').status_code == 200


def test_replay_checks_current_permissions_before_starting_mcp(demo_api, sdk_python, monkeypatch):
    client, ids, sessions = demo_api
    source = client.post(f'/agents/{ids["mcp_agent_id"]}/chat', json={"message": "Get order DEMO-1001"}).json()
    with sessions() as db:
        db.get(Agent, ids["mcp_agent_id"]).allowed_tools = "[]"
        db.commit()
    monkeypatch.setattr(MCPOrderTool, "run", lambda *args: pytest.fail("Revoked permission must block MCP"))
    response = client.post(f'/executions/{source["execution_id"]}/replay', json={})
    assert response.status_code == 500
    assert response.json()["detail"]["failure_type"] == "tool_permission_denied"
    failed_replay = client.get(f'/executions/{source["execution_id"]}/replays').json()[0]
    assert failed_replay["status"] == "failed"
    assert failed_replay["failure_type"] == "tool_permission_denied"


def test_planner_and_executor_both_enforce_order_permissions(demo_api, monkeypatch):
    client, ids, _ = demo_api
    monkeypatch.setattr(MCPOrderTool, "run", lambda *args: pytest.fail("MCP must not run without permission"))
    reply = client.post(f'/agents/{ids["agent_id"]}/chat', json={"message": "Get order DEMO-1001"}).json()
    assert reply["status"] == "completed" and reply["response"].startswith("[MOCK]")
    trace = client.get(f'/executions/{reply["execution_id"]}/trace').json()
    assert all(event["tool"] is None for event in trace)
    monkeypatch.setattr(agent_runner, "plan_execution", lambda *args, **kwargs: ExecutionPlan(
        steps=[ExecutionStep(tool="get_order", arguments={"order_id": "DEMO-1001"}, input="forced")],
    ))
    forced = client.post(f'/agents/{ids["agent_id"]}/chat', json={"message": "forced"}).json()
    assert forced["status"] == "failed"
    record = client.get(f'/executions/{forced["execution_id"]}').json()
    assert record["failure_type"] == "tool_permission_denied"
