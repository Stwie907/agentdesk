from app.runtime.executor import execute_tool
from app.runtime.planner import plan


def test_execution_pipeline_calculator():
    task = plan("计算12345*6789")

    assert task["tool"] == "calculator"

    result = execute_tool(
        task["tool"],
        task["input"],
    )

    assert result == "83810205"


def test_execution_pipeline_datetime():
    task = plan("现在几点？")

    assert task["tool"] == "datetime"

    result = execute_tool(
        task["tool"],
        task["input"],
    )

    assert isinstance(result, str)
    assert len(result) > 0


def test_execution_pipeline_normal_chat(monkeypatch):
    from app.services import agent_runner

    monkeypatch.setattr(
        agent_runner,
        "run_agent",
        lambda *args, **kwargs: "mock response"
    )

    task = plan("介绍一下AgentDesk项目")

    assert task["tool"] is None
    assert task["input"] == "介绍一下AgentDesk项目"
