from app.runtime.execution_plan import ExecutionPlan, ExecutionStep


def test_execution_plan_can_represent_agent_runner_tool_step():
    """
    Runtime V4 contract:

    Agent runner should be able to consume an ExecutionPlan whose first
    step contains a structured tool call.
    """

    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool="calculator",
                arguments={
                    "expression": "12+34",
                },
                input="计算12+34",
            )
        ]
    )

    assert len(plan.steps) == 1

    step = plan.steps[0]

    assert step.tool == "calculator"
    assert step.arguments == {
        "expression": "12+34",
    }
    assert step.input == "计算12+34"


def test_execution_plan_can_represent_agent_runner_no_tool_step():
    """
    A no-tool planner decision must remain representable inside the
    Runtime V4 execution-plan contract.
    """

    plan = ExecutionPlan(
        steps=[
            ExecutionStep(
                tool=None,
                arguments={},
                input="介绍一下 AgentDesk",
            )
        ]
    )

    step = plan.steps[0]

    assert step.tool is None
    assert step.arguments == {}
    assert step.input == "介绍一下 AgentDesk"
