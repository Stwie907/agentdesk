import pytest

from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.runtime.executor import ToolPermissionDenied
from app.runtime.plan_executor import (
    PlanExecutionResult,
    execute_plan,
    execute_step,
)


def test_execute_step_runs_tool():
    step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": "12+34",
        },
        input="计算12+34",
    )

    result = execute_step(
        step,
        allowed_tools=["calculator"],
    )

    assert result.step == step
    assert result.output == "46"


def test_execute_step_supports_no_tool_step():
    step = ExecutionStep(
        tool=None,
        arguments={},
        input="介绍一下 AgentDesk",
    )

    result = execute_step(step)

    assert result.step == step
    assert result.output is None


def test_execute_plan_executes_steps_in_order():
    first_step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": "1+1",
        },
        input="计算1+1",
    )

    second_step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": "10+5",
        },
        input="计算10+5",
    )

    plan = ExecutionPlan(
        steps=[
            first_step,
            second_step,
        ]
    )

    result = execute_plan(
        plan,
        allowed_tools=["calculator"],
    )

    assert isinstance(result, PlanExecutionResult)
    assert len(result.steps) == 2

    assert result.steps[0].step == first_step
    assert result.steps[0].output == "2"

    assert result.steps[1].step == second_step
    assert result.steps[1].output == "15"


def test_execute_plan_respects_tool_permissions():
    step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": "1+1",
        },
        input="计算1+1",
    )

    plan = ExecutionPlan(
        steps=[step]
    )

    with pytest.raises(ToolPermissionDenied):
        execute_plan(
            plan,
            allowed_tools=[],
        )


def test_execute_plan_supports_empty_plan():
    plan = ExecutionPlan()

    result = execute_plan(plan)

    assert result.steps == []
    assert result.last_output is None


def test_plan_execution_result_returns_last_output():
    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": "2+3",
                },
                input="计算2+3",
            ),
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": "4+5",
                },
                input="计算4+5",
            ),
        ]
    )

    result = execute_plan(
        plan,
        allowed_tools=["calculator"],
    )

    assert result.last_output == "9"

def test_execute_plan_resolves_previous_step_output_in_later_step_arguments(
    monkeypatch,
):
    first_step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": "1+1",
        },
        input="计算1+1",
    )

    second_step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": {
                "$step_output": 0,
            },
        },
        input="使用上一步结果",
    )

    plan = ExecutionPlan(
        steps=[
            first_step,
            second_step,
        ]
    )

    calls = []

    def fake_execute_tool(
        tool_name,
        tool_input,
        allowed_tools=None,
    ):
        calls.append(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "allowed_tools": allowed_tools,
            }
        )

        if len(calls) == 1:
            return "2"

        return tool_input["expression"]

    monkeypatch.setattr(
        "app.runtime.plan_executor.execute_tool",
        fake_execute_tool,
    )

    result = execute_plan(
        plan,
        allowed_tools=["calculator"],
    )

    assert len(calls) == 2

    assert calls[0]["tool_input"] == {
        "expression": "1+1",
    }

    assert calls[1]["tool_input"] == {
        "expression": "2",
    }

    assert result.steps[0].output == "2"
    assert result.steps[1].output == "2"
    assert result.last_output == "2"

def test_execute_plan_rejects_invalid_step_output_reference():
    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": {
                        "$step_output": 0,
                    },
                },
                input="使用不存在的上一步结果",
            ),
        ]
    )

    with pytest.raises(
        ValueError,
        match="Invalid step output reference: 0",
    ):
        execute_plan(
            plan,
            allowed_tools=["calculator"],
        )

def test_execute_plan_resolves_step_output_inside_nested_arguments(monkeypatch):
    calls = []

    def fake_execute_tool(tool_name, tool_input, allowed_tools=None):
        calls.append(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
            }
        )

        if len(calls) == 1:
            return "first-result"

        return "second-result"

    monkeypatch.setattr(
        "app.runtime.plan_executor.execute_tool",
        fake_execute_tool,
    )

    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="first_tool",
                arguments={
                    "value": "hello",
                },
                input="first step",
            ),
            ExecutionStep(
                tool="second_tool",
                arguments={
                    "payload": {
                        "previous": {
                            "$step_output": 0,
                        }
                    }
                },
                input="second step",
            ),
        ]
    )

    result = execute_plan(
        plan,
        allowed_tools=[
            "first_tool",
            "second_tool",
        ],
    )

    assert len(calls) == 2

    assert calls[1]["tool_input"] == {
        "payload": {
            "previous": "first-result",
        }
    }

    assert result.last_output == "second-result"

def test_execute_plan_resolves_step_output_inside_list_arguments(monkeypatch):
    calls = []

    def fake_execute_tool(tool_name, tool_input, allowed_tools=None):
        calls.append(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
            }
        )

        if len(calls) == 1:
            return "first-result"

        return "second-result"

    monkeypatch.setattr(
        "app.runtime.plan_executor.execute_tool",
        fake_execute_tool,
    )

    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="first_tool",
                arguments={
                    "value": "hello",
                },
                input="first step",
            ),
            ExecutionStep(
                tool="second_tool",
                arguments={
                    "items": [
                        "before",
                        {
                            "$step_output": 0,
                        },
                        "after",
                    ]
                },
                input="second step",
            ),
        ]
    )

    result = execute_plan(
        plan,
        allowed_tools=[
            "first_tool",
            "second_tool",
        ],
    )

    assert len(calls) == 2

    assert calls[1]["tool_input"] == {
        "items": [
            "before",
            "first-result",
            "after",
        ]
    }

    assert result.last_output == "second-result"

def test_execute_plan_rejects_current_or_future_step_output_reference(monkeypatch):
    calls = []

    def fake_execute_tool(tool_name, tool_input, allowed_tools=None):
        calls.append(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
            }
        )
        return "result"

    monkeypatch.setattr(
        "app.runtime.plan_executor.execute_tool",
        fake_execute_tool,
    )

    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="first_tool",
                arguments={
                    "value": {
                        "$step_output": 0,
                    }
                },
                input="first step",
            ),
            ExecutionStep(
                tool="second_tool",
                arguments={},
                input="second step",
            ),
        ]
    )

    with pytest.raises(ValueError):
        execute_plan(
            plan,
            allowed_tools=[
                "first_tool",
                "second_tool",
            ],
        )

    assert calls == []
