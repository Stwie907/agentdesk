from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExecutionStep:
    """
    One executable step inside an ExecutionPlan.

    tool:
        Name of the tool to execute.
        None means the step does not require a tool.

    arguments:
        Structured arguments passed to the tool.

    input:
        Original or normalized input associated with this step.
    """

    tool: str | None
    arguments: dict[str, Any] = field(default_factory=dict)
    input: str = ""


@dataclass
class ExecutionPlan:
    """
    Internal runtime representation of a planned execution.

    The planner currently produces one tool decision.
    ExecutionPlan wraps that existing decision as a list of steps,
    allowing the runtime to support multiple steps later without
    breaking the Planner V4 contract.
    """

    steps: list[ExecutionStep] = field(default_factory=list)

    def is_empty(self) -> bool:
        return len(self.steps) == 0


def execution_plan_from_task(
    task: dict[str, Any],
    user_input: str,
) -> ExecutionPlan:
    """
    Convert the existing Planner V4 task contract into an ExecutionPlan.

    Existing Planner V4 contract:

        {
            "tool": str | None,
            "arguments": dict,
            "input": str,
        }

    This adapter deliberately keeps planner.py unchanged.
    """

    tool_name = task.get("tool")

    arguments = task.get("arguments")
    if not isinstance(arguments, dict):
        arguments = {}

    task_input = task.get("input", user_input)

    step = ExecutionStep(
        tool=tool_name,
        arguments=arguments,
        input=task_input,
    )

    return ExecutionPlan(
        steps=[step],
    )
