from app.runtime.execution_plan import (
    ExecutionPlan,
    ExecutionStep,
    execution_plan_from_task,
)


def test_execution_step_stores_structured_tool_call():
    step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": "12+34",
        },
        input="计算12+34",
    )

    assert step.tool == "calculator"
    assert step.arguments == {
        "expression": "12+34",
    }
    assert step.input == "计算12+34"


def test_execution_plan_contains_steps():
    step = ExecutionStep(
        tool="calculator",
        arguments={
            "expression": "1+1",
        },
        input="计算1+1",
    )

    plan = ExecutionPlan(
        steps=[step],
    )

    assert len(plan.steps) == 1
    assert plan.steps[0] == step
    assert plan.is_empty() is False


def test_empty_execution_plan_is_empty():
    plan = ExecutionPlan()

    assert plan.steps == []
    assert plan.is_empty() is True


def test_execution_plan_from_v4_structured_task():
    task = {
        "tool": "calculator",
        "arguments": {
            "expression": "12+34",
        },
        "input": "12+34",
    }

    plan = execution_plan_from_task(
        task,
        user_input="计算12+34",
    )

    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert step.tool == "calculator"
    assert step.arguments == {
        "expression": "12+34",
    }
    assert step.input == "12+34"


def test_execution_plan_from_v4_no_tool_task():
    task = {
        "tool": None,
        "arguments": {},
        "input": "介绍一下 AgentDesk",
    }

    plan = execution_plan_from_task(
        task,
        user_input="介绍一下 AgentDesk",
    )

    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert step.tool is None
    assert step.arguments == {}
    assert step.input == "介绍一下 AgentDesk"


def test_execution_plan_normalizes_invalid_arguments():
    task = {
        "tool": "calculator",
        "arguments": None,
        "input": "1+1",
    }

    plan = execution_plan_from_task(
        task,
        user_input="计算1+1",
    )

    assert plan.steps[0].arguments == {}


def test_execution_plan_falls_back_to_user_input():
    task = {
        "tool": None,
        "arguments": {},
    }

    plan = execution_plan_from_task(
        task,
        user_input="hello",
    )

    assert plan.steps[0].input == "hello"
