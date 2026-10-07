import re
from typing import Any


# The demo planner supports one binary arithmetic operation, not open-ended
# natural-language planning. Its selected tools still execute normally.
NUMBER = r"[+-]?[0-9]+(?:\.[0-9]+)?"
CALCULATION = re.compile(
    rf"(?:(?:计算|calculate)\s*)?({NUMBER}\s*[+\-*/]\s*{NUMBER})[?？]?",
    re.IGNORECASE,
)


def plan_mock_task(
    user_input: str,
    allowed_tools: list[str],
) -> dict[str, Any]:
    task: dict[str, Any] = {
        "tool": None,
        "arguments": {},
        "input": user_input,
    }
    match = CALCULATION.fullmatch(user_input.strip())

    if match is not None and "calculator" in allowed_tools:
        task["tool"] = "calculator"
        task["arguments"] = {
            "expression": re.sub(r"\s+", "", match.group(1)),
        }

    return task
