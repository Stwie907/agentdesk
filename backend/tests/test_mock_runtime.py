import json

import pytest
import requests
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.agent import Agent
from app.models.project import Project
from app.models.user import User
from app.services import agent_runner, llm_provider
from app.tools import registry
from app.tools.calculator import CalculatorTool
from app.workers import execution_worker


@pytest.fixture
def mock_runtime_api(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    sessions = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with sessions() as db:
        user = User(username="mock-demo-user", email="mock-demo@example.com")
        db.add(user)
        db.flush()
        project = Project(name="mock-demo-project", owner_id=user.id)
        db.add(project)
        db.flush()
        agent = Agent(
            name="mock-demo-agent",
            project_id=project.id,
            model="unused-model",
            allowed_tools=json.dumps(["calculator"]),
        )
        db.add(agent)
        db.commit()
        agent_id = agent.id

    def override_db():
        with sessions() as db:
            yield db

    def forbid_request(*args, **kwargs):
        raise AssertionError("The offline demo must not send HTTP requests")

    monkeypatch.setitem(app.dependency_overrides, get_db, override_db)
    monkeypatch.setattr(execution_worker, "SessionLocal", sessions)
    monkeypatch.setattr(agent_runner, "SessionLocal", sessions)
    monkeypatch.setitem(registry._registry, "calculator", CalculatorTool())
    monkeypatch.setattr(requests.sessions.Session, "request", forbid_request)

    try:
        with TestClient(app) as client:
            yield client, agent_id, sessions
    finally:
        engine.dispose()


def submit_demo(client, agent_id, message):
    response = client.post(f"/agents/{agent_id}/chat", json={"message": message})
    assert response.status_code == 200
    return response.json()


def test_mock_chat_executes_real_calculator_and_persists_trace_snapshot_history(mock_runtime_api):
    client, agent_id, _ = mock_runtime_api
    body = submit_demo(client, agent_id, "计算40+2")
    execution_id = body["execution_id"]
    assert body["status"] == "completed"
    assert body["response"] == "42"

    execution = client.get(f"/executions/{execution_id}").json()
    assert execution["output"] == "42"
    assert execution["failure_type"] is None
    trace = client.get(f"/executions/{execution_id}/trace").json()
    assert [event["event"] for event in trace] == [
        "plan_started", "step_started", "step_completed", "plan_completed",
    ]
    assert "provider=mock" in trace[0]["message"]
    assert trace[1]["tool"] == "calculator"

    snapshot = client.get(f"/executions/{execution_id}/snapshot").json()
    assert snapshot["snapshot_version"] == 1
    assert snapshot["input_snapshot"] == "计算40+2"
    assert snapshot["output_snapshot"] == "42"
    assert json.loads(snapshot["plan_snapshot"])["steps"][0]["arguments"] == {
        "expression": "40+2",
    }
    history = client.get(f"/executions?agent_id={agent_id}").json()
    assert len(history) == 1
    assert history[0]["id"] == execution_id


def test_mock_no_tool_reply_is_explicitly_marked_and_has_a_snapshot(mock_runtime_api):
    client, agent_id, _ = mock_runtime_api
    body = submit_demo(client, agent_id, "Hello AgentDesk")
    assert body["status"] == "completed"
    assert body["response"] == llm_provider.MOCK_RESPONSE
    snapshot = client.get(f"/executions/{body['execution_id']}/snapshot").json()
    assert snapshot["output_snapshot"] == llm_provider.MOCK_RESPONSE
    assert json.loads(snapshot["plan_snapshot"])["steps"][0]["tool"] is None


def test_mock_runtime_respects_agent_tool_permissions(mock_runtime_api, monkeypatch):
    client, agent_id, sessions = mock_runtime_api
    with sessions() as db:
        agent = db.get(Agent, agent_id)
        agent.allowed_tools = "[]"
        db.commit()

    def forbid_calculation(*args, **kwargs):
        raise AssertionError("A disallowed Calculator must not execute")

    monkeypatch.setattr(CalculatorTool, "run", forbid_calculation)
    body = submit_demo(client, agent_id, "计算40+2")
    assert body["status"] == "completed"
    assert body["response"] == llm_provider.MOCK_RESPONSE


def test_mock_calculator_replay_remains_offline_after_switching_provider(mock_runtime_api, monkeypatch):
    client, agent_id, _ = mock_runtime_api
    source = submit_demo(client, agent_id, "Calculate 40 + 2")
    monkeypatch.setenv("LLM_PROVIDER", "ollama")

    def forbid_planning(*args, **kwargs):
        raise AssertionError("Replay must use the stored plan")

    monkeypatch.setattr(agent_runner, "plan_execution", forbid_planning)
    response = client.post(f"/executions/{source['execution_id']}/replay")
    assert response.status_code == 200
    replay = response.json()
    assert replay["id"] != source["execution_id"]
    assert replay["replay_of_execution_id"] == source["execution_id"]
    assert replay["status"] == "completed"
    assert replay["output"] == "42"
    snapshot = client.get(f"/executions/{replay['id']}/snapshot").json()
    assert snapshot["output_snapshot"] == "42"
    second_replay = client.post(f"/executions/{replay['id']}/replay").json()
    assert second_replay["status"] == "completed"
    assert second_replay["output"] == "42"
    assert second_replay["replay_of_execution_id"] == replay["id"]


def test_ollama_timeout_is_persisted_as_failed_instead_of_switching_to_mock(mock_runtime_api, monkeypatch):
    client, agent_id, _ = mock_runtime_api
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    requests_sent = []

    def timeout_post(*args, **kwargs):
        requests_sent.append(kwargs)
        raise requests.Timeout("demo timeout")

    monkeypatch.setattr(llm_provider.requests, "post", timeout_post)
    body = submit_demo(client, agent_id, "计算40+2")
    assert body["status"] == "failed"
    assert "[MOCK]" not in body["response"]
    execution = client.get(f"/executions/{body['execution_id']}").json()
    assert execution["failure_type"] == "timeout"
    assert execution["retry_count"] == 2
    assert len(requests_sent) == 3
