import re


class CalculatorTool:

    name = "calculator"

    def run(self, expression: str):

        try:
            # 提取数学表达式
            match = re.search(
                r"[0-9\+\-\*\/\(\)\.]+",
                expression
            )

            if not match:
                return "无法识别计算表达式"

            expr = match.group()

            result = eval(expr)

            return str(result)

        except Exception as e:
            return f"Calculation error: {e}"
