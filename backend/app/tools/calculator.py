import re
from typing import Any, Dict, Union

from app.tools.base import BaseTool


class CalculatorTool(BaseTool):
    name = "calculator"

    description = (
        "Perform basic mathematical calculations from a user expression."
    )

    input_schema = {
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": (
                    "A mathematical expression such as "
                    "12345*6789 or (10+2)/3."
                ),
            },
        },
        "required": ["expression"],
        "additionalProperties": False,
    }

    def run(
        self,
        arguments: Union[str, Dict[str, Any]],
    ) -> str:
        # Backward compatibility with the old string contract.
        if isinstance(arguments, str):
            expression = arguments
        else:
            expression = arguments["expression"]

        try:
            match = re.search(
                r"[0-9+\-*/().]+",
                expression,
            )

            if not match:
                return "无法识别计算表达式"

            expr = match.group()

            result = eval(
                expr,
                {
                    "__builtins__": {},
                },
                {},
            )

            return str(result)

        except Exception as e:
            return f"Calculation error: {e}"
