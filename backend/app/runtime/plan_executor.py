from dataclasses import dataclass, field
from typing import Any

from app.runtime.execution_plan import ExecutionPlan, ExecutionStep
from app.runtime.executor import execute_tool

def resolve_step_outputs(
    value: Any,
    previous_results: list["StepExecutionResult"],
) -> Any:
    """
    Resolve step-output references inside execution arguments.

    Supported reference format:

        {
            "$step_output": 0
        }

    The integer points to an earlier step result by zero-based index.

    Resolution is recursive, so references may appear inside nested
    dictionaries or lists.
    """

    if isinstance(value, dict):
        if set(value.keys()) == {"$step_output"}:
            step_index = value["$step_output"]

            if not isinstance(step_index, int):
                raise ValueError(
                    "$step_output must contain an integer step index"
                )

            if step_index < 0 or step_index >= len(previous_results):
                raise ValueError(
                    f"Invalid step output reference: {step_index}"
                )

            return previous_results[step_index].output

        return {
            key: resolve_step_outputs(
                item,
                previous_results,
            )
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [
            resolve_step_outputs(
                item,
                previous_results,
            )
            for item in value
        ]

    return value

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

    Later steps may reference outputs produced by earlier steps through:

        {
            "$step_output": <step index>
        }

    Tool permissions and tool execution errors are still delegated to
    app.runtime.executor.execute_tool().
    """

    results: list[StepExecutionResult] = []

    for step in plan.steps:
        resolved_arguments = resolve_step_outputs(
            step.arguments,
            results,
        )

        resolved_step = ExecutionStep(
            tool=step.tool,
            arguments=resolved_arguments,
            input=step.input,
        )

        result = execute_step(
            resolved_step,
            allowed_tools=allowed_tools,
        )

        results.append(result)

    return PlanExecutionResult(
        steps=results,
    )
