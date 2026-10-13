from app.runtime.executor import execute_tool
import app.runtime.planner as planner


def fake_plan(user_input):

    if "12345*6789" in user_input:
        return {
            "tool": "calculator",
            "input": "12345*6789"
        }


    if "现在几点" in user_input:
        return {
            "tool": "datetime",
            "input": ""
        }


    return {
        "tool": None,
        "input": user_input
    }



def test_execution_pipeline_calculator(monkeypatch):

    monkeypatch.setattr(
        planner,
        "plan",
        fake_plan
    )


    task = fake_plan(
        "计算12345*6789"
    )


    assert task["tool"] == "calculator"


    result = execute_tool(
        task["tool"],
        task["input"]
    )


    assert result == "83810205"



def test_execution_pipeline_datetime(monkeypatch):

    monkeypatch.setattr(
        planner,
        "plan",
        fake_plan
    )


    task = fake_plan(
        "现在几点？"
    )


    assert task["tool"] == "datetime"


    result = execute_tool(
        task["tool"],
        task["input"]
    )


    assert isinstance(result, str)

    assert len(result) > 0



def test_execution_pipeline_normal_chat(monkeypatch):

    monkeypatch.setattr(
        planner,
        "plan",
        fake_plan
    )


    task = fake_plan(
        "介绍一下AgentDesk项目"
    )


    assert task["tool"] is None

    assert task["input"] == "介绍一下AgentDesk项目"
