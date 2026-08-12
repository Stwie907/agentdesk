from app.tools.calculator import CalculatorTool
from app.tools.datetime_tool import DateTimeTool


tools = [
    CalculatorTool(),
    DateTimeTool(),
]


def get_tool(name):
    for tool in tools:
        if tool.name == name:
            return tool

    return None
