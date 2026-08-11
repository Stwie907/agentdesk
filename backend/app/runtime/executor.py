from app.tools.registry import get_tool


def execute_tool(tool_name: str, input: str):

    tool = get_tool(tool_name)

    if not tool:
        return "Tool not found"

    return tool.run(input)

