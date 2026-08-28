from typing import Dict, List, Optional

from app.tools.base import BaseTool
from app.tools.calculator import CalculatorTool
from app.tools.datetime_tool import DateTimeTool


_registry: Dict[str, BaseTool] = {}


def register_tool(tool: BaseTool) -> None:
    """
    Register one tool by its unique name.
    """

    if not isinstance(tool, BaseTool):
        raise TypeError("tool must be an instance of BaseTool")

    if not tool.name:
        raise ValueError("tool name must not be empty")

    _registry[tool.name] = tool


def get_tool(name: str) -> Optional[BaseTool]:
    """
    Return one registered tool by name.
    """

    return _registry.get(name)


def list_tools() -> List[BaseTool]:
    """
    Return all registered tools.
    """

    return list(_registry.values())


def get_tool_metadata(name: str) -> Optional[dict]:
    """
    Return public metadata for one registered tool.
    """

    tool = get_tool(name)

    if tool is None:
        return None

    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def list_tool_metadata() -> List[dict]:
    """
    Return metadata for all registered tools.
    """

    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.input_schema,
        }
        for tool in list_tools()
    ]


# Register built-in AgentDesk tools.
register_tool(CalculatorTool())
register_tool(DateTimeTool())
