import re
from typing import Any


# The demo planner supports fixed arithmetic and order lookup rules.
# Selected tools execute normally; this is not general language planning.
NUMBER = r"[+-]?[0-9]+(?:\.[0-9]+)?"
CALCULATION = re.compile(
    rf"(?:(?:计算|calculate)\s*)?({NUMBER}\s*[+\-*/]\s*{NUMBER})[?？]?",
    re.IGNORECASE,
)
ORDER_LOOKUP = re.compile(
    r"(?:get\s+order\s+|查询订单\s*)(DEMO-[0-9]{4})[?？]?",
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
    order = ORDER_LOOKUP.fullmatch(user_input.strip())
    if order is not None and "get_order" in allowed_tools:
        task["tool"] = "get_order"
        task["arguments"] = {"order_id": order.group(1).upper()}
        return task
    match = CALCULATION.fullmatch(user_input.strip())

    if match is not None and "calculator" in allowed_tools:
        task["tool"] = "calculator"
        task["arguments"] = {
            "expression": re.sub(r"\s+", "", match.group(1)),
        }

    return task
