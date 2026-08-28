from typing import Any, Dict, List, Optional, Union

from app.tools.base import ToolArgumentsError
from app.tools.registry import get_tool


class ToolPermissionDenied(Exception):
    """
    Raised when an Agent tries to execute a tool that it is not
    allowed to use.
    """

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(
            f"Tool '{tool_name}' is not allowed for this agent"
        )


def execute_tool(
    tool_name: str,
    input: Union[str, Dict[str, Any]],
    allowed_tools: Optional[List[str]] = None,
):
    """
    Execute a registered tool.

    Responsibilities:
    - verify tool permission
    - find the tool from the registry
    - delegate argument validation to the tool contract
    - execute the tool
    - return the result

    The executor deliberately contains no tool-specific logic.
    """

    if (
        allowed_tools is not None
        and tool_name not in allowed_tools
    ):
        raise ToolPermissionDenied(tool_name)

    tool = get_tool(tool_name)

    if not tool:
        return "Tool not found"

    return tool.execute(input)
