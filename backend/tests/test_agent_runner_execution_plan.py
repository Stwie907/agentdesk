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

def test_run_agent_delegates_execution_to_plan_executor(monkeypatch):
    import app.services.agent_runner as agent_runner

    calls = {
        "execute_plan": 0,
    }

    class FakePlanResult:
        last_output = "42"
        steps = []

    monkeypatch.setattr(
        agent_runner,
        "plan_execution",
        lambda *args, **kwargs: ExecutionPlan(
            steps=[
                ExecutionStep(
                    tool="calculator",
                    arguments={
                        "expression": "40+2",
                    },
                    input="40+2",
                )
            ]
        ),
    )
    def fake_execute_plan(
        plan,
        allowed_tools=None,
        on_step_started=None,
        on_step_completed=None,
        on_step_failed=None,
    ):
        calls["execute_plan"] += 1

        assert len(plan.steps) == 1
        assert plan.steps[0].tool == "calculator"
        assert plan.steps[0].arguments == {
            "expression": "40+2",
        }

        return FakePlanResult()

    monkeypatch.setattr(
        agent_runner,
        "execute_plan",
        fake_execute_plan,
    )

    result = agent_runner.run_agent(
        "qwen2.5:7b",
        "计算40+2",
        allowed_tools=["calculator"],
    )

    assert calls["execute_plan"] == 1
    assert result == "42"
