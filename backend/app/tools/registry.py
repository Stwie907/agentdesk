from app.tools.calculator import CalculatorTool


tools = [
    CalculatorTool()
]


def get_tool(name):

    for tool in tools:
        if tool.name == name:
            return tool

    return None

