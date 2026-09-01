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
