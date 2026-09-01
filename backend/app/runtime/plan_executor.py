from dataclasses import dataclass, field
from typing import Any

from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.runtime.executor import execute_tool


@dataclass
class StepExecutionResult:
    """
    Result produced by executing one ExecutionStep.
    """

    step: ExecutionStep
    output: Any = None


@dataclass
class PlanExecutionResult:
    """
    Result produced by executing an ExecutionPlan.

    Results are kept in the same order as the plan steps.
    """

    steps: list[StepExecutionResult] = field(default_factory=list)

    @property
    def last_output(self) -> Any:
        if not self.steps:
            return None

        return self.steps[-1].output


def execute_step(
    step: ExecutionStep,
    allowed_tools: list[str] | None = None,
) -> StepExecutionResult:
    """
    Execute one ExecutionStep.

    Tool-backed steps delegate to the existing runtime tool executor.
    No-tool steps do not invoke a tool.
    """

    if step.tool is None:
        return StepExecutionResult(
            step=step,
            output=None,
        )

    output = execute_tool(
        step.tool,
        step.arguments,
        allowed_tools=allowed_tools,
    )

    return StepExecutionResult(
        step=step,
        output=output,
    )


def execute_plan(
    plan: ExecutionPlan,
    allowed_tools: list[str] | None = None,
) -> PlanExecutionResult:
    """
    Execute every step in an ExecutionPlan in order.

    Tool permissions and tool execution errors are delegated to
    app.runtime.executor.execute_tool().
    """

    results: list[StepExecutionResult] = []

    for step in plan.steps:
        result = execute_step(
            step,
            allowed_tools=allowed_tools,
        )
        results.append(result)

    return PlanExecutionResult(
        steps=results,
    )
