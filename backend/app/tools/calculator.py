import re

from app.tools.base import BaseTool


class CalculatorTool(BaseTool):
    name = "calculator"

    description = (
        "Perform basic mathematical calculations from a user expression."
    )

    input_schema = {
        "type": "string",
        "description": (
            "A mathematical expression such as 12345*6789 or (10+2)/3."
        ),
    }

    def run(self, expression: str) -> str:
        try:
            # Extract only a basic mathematical expression.
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
