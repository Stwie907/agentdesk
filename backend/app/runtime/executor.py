from typing import Any, Dict, List, Optional, Union

from app.tools.base import ToolArgumentsError
from app.tools.registry import get_tool


class ToolError(Exception):
    """
    Base exception for tool execution failures.
    """


class ToolNotFoundError(ToolError):
    """
    Raised when the requested tool does not exist in the registry.
    """

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"Tool '{tool_name}' not found")


class ToolPermissionDenied(ToolError):
    """
    Raised when an Agent tries to execute a tool that it is not
    allowed to use.
    """

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(
            f"Tool '{tool_name}' is not allowed for this agent"
        )


class ToolExecutionError(ToolError):
    """
    Raised when a registered tool fails during execution.
    """

    def __init__(self, tool_name: str, message: str):
        self.tool_name = tool_name
        self.original_message = message
        super().__init__(
            f"Tool '{tool_name}' execution failed: {message}"
        )


def execute_tool(
    tool_name: str,
    input: Union[str, Dict[str, Any]],
    allowed_tools: Optional[List[str]] = None,
):
    """
    Execute a registered tool.

    Error contract:
    - ToolPermissionDenied:
      the tool exists conceptually but the Agent is not allowed to use it.
    - ToolNotFoundError:
      the requested tool is not registered.
    - ToolArgumentsError:
      the tool received invalid arguments.
    - ToolExecutionError:
      the tool itself failed while executing.

    ToolArgumentsError is deliberately allowed to propagate unchanged
    because it already represents a structured tool-contract failure.
    """

    if (
        allowed_tools is not None
        and tool_name not in allowed_tools
    ):
        raise ToolPermissionDenied(tool_name)

    tool = get_tool(tool_name)

    if not tool:
        raise ToolNotFoundError(tool_name)

    try:
        return tool.execute(input)

    except ToolArgumentsError:
        raise

    except Exception as exc:
        raise ToolExecutionError(
            tool_name,
            str(exc),
        ) from exc
