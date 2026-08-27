from typing import Optional

from app.tools.registry import get_tool


class ToolPermissionDenied(Exception):
    """
    Raised when an Agent tries to execute a tool that it is not
    allowed to use.
    """

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' is not allowed for this agent")


def execute_tool(
    tool_name: str,
    input: str,
    allowed_tools: Optional[list[str]] = None,
):
    """
    Execute a registered tool.

    Responsibilities:
    - verify tool permission
    - find the tool from the registry
    - execute the tool
    - return the tool result

    Permission behavior:
    - allowed_tools=None keeps backward compatibility
    - when allowed_tools is provided, the requested tool must
      explicitly appear in the list

    Database execution lifecycle and logging are handled
    by the worker/runtime layer, not by the tool executor.
    """

    if allowed_tools is not None and tool_name not in allowed_tools:
        raise ToolPermissionDenied(tool_name)

    tool = get_tool(tool_name)

    if not tool:
        return "Tool not found"

    return tool.run(input)
