from app.tools.registry import get_tool


def execute_tool(tool_name: str, input: str):
    """
    Execute a registered tool.

    Responsibilities:
    - find the tool from the registry
    - execute the tool
    - return the tool result

    Database execution lifecycle and logging are handled
    by the worker layer, not by the tool executor.
    """

    tool = get_tool(tool_name)

    if not tool:
        return "Tool not found"

    return tool.run(input)
