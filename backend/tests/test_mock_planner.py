import pytest
import requests

from app.runtime import planner


@pytest.fixture
def offline_mock(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")

    def forbid_request(*args, **kwargs):
        raise AssertionError("Mock planning must be offline")

    monkeypatch.setattr(requests.sessions.Session, "request", forbid_request)


@pytest.mark.parametrize("user_input, expression", [
    ("计算40+2", "40+2"),
    ("Calculate 40 + 2", "40+2"),
    ("40+2", "40+2"),
    ("计算 -4.5 * 2", "-4.5*2"),
])
def test_mock_demo_plans_are_deterministic_and_use_structured_arguments(
    offline_mock, user_input, expression,
):
    expected = {
        "tool": "calculator",
        "arguments": {"expression": expression},
        "input": user_input,
    }
    assert planner.plan(user_input, allowed_tools=["calculator"]) == expected
    assert planner.plan(user_input, allowed_tools=["calculator"]) == expected
    execution_plan = planner.plan_execution(user_input, allowed_tools=["calculator"])
    assert len(execution_plan.steps) == 1
    assert execution_plan.steps[0].tool == "calculator"
    assert execution_plan.steps[0].arguments == expected["arguments"]
    assert execution_plan.steps[0].input == user_input


@pytest.mark.parametrize("allowed_tools", [[], ["datetime"], ["unknown"]])
def test_mock_planner_never_selects_a_disallowed_tool(offline_mock, allowed_tools):
    assert planner.plan("计算40+2", allowed_tools=allowed_tools)["tool"] is None
    assert planner.plan_execution("计算40+2", allowed_tools=allowed_tools).steps[0].tool is None


@pytest.mark.parametrize("user_input", ["Hello AgentDesk", "现在几点？", "计算40+2再乘3"])
def test_unsupported_demo_tasks_use_no_tool(offline_mock, user_input):
    assert planner.plan(user_input, allowed_tools=None) == {
        "tool": None, "arguments": {}, "input": user_input,
    }
