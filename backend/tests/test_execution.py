from app.runtime.executor import execute_tool
from app.runtime.planner import plan
import app.services.agent_runner as agent_runner

def fake_run_agent(model, prompt):
    return "mock agent response"


def test_execution_pipeline_calculator(monkeypatch):

    monkeypatch.setattr(
        agent_runner,
        "run_agent",
        fake_run_agent
    )
    task = plan("计算12345*6789")

    assert task["tool"] == "calculator"

    result = execute_tool(
        task["tool"],
        task["input"],
    )

    assert result == "83810205"


def test_execution_pipeline_datetime(monkeypatch):

    monkeypatch.setattr(
        agent_runner,
        "run_agent",
        fake_run_agent
    )
    task = plan("现在几点？")

    assert task["tool"] == "datetime"

    result = execute_tool(
        task["tool"],
        task["input"],
    )

    assert isinstance(result, str)
    assert len(result) > 0


def test_execution_pipeline_normal_chat(monkeypatch):

    monkeypatch.setattr(
    agent_runner,
    "run_agent",
    fake_run_agent
)
    task = plan("介绍一下AgentDesk项目")

    assert task["tool"] is None
    assert task["input"] == "介绍一下AgentDesk项目"
