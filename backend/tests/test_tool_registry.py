from app.tools.base import BaseTool
from app.tools.calculator import CalculatorTool
from app.tools.datetime_tool import DateTimeTool
from app.tools.registry import get_tool


def test_calculator_is_base_tool():
    tool = CalculatorTool()

    assert isinstance(tool, BaseTool)


def test_datetime_is_base_tool():
    tool = DateTimeTool()

    assert isinstance(tool, BaseTool)


def test_calculator_metadata():
    tool = CalculatorTool()

    assert tool.name == "calculator"
    assert isinstance(tool.description, str)
    assert tool.description.strip() != ""

    assert isinstance(tool.input_schema, dict)
    assert "type" in tool.input_schema


def test_datetime_metadata():
    tool = DateTimeTool()

    assert tool.name == "datetime"
    assert isinstance(tool.description, str)
    assert tool.description.strip() != ""

    assert isinstance(tool.input_schema, dict)
    assert "type" in tool.input_schema


def test_registry_returns_calculator():
    tool = get_tool("calculator")

    assert tool is not None
    assert isinstance(tool, CalculatorTool)


def test_registry_returns_datetime():
    tool = get_tool("datetime")

    assert tool is not None
    assert isinstance(tool, DateTimeTool)


def test_registry_returns_none_for_unknown_tool():
    tool = get_tool("does-not-exist")

    assert tool is None

from app.tools.registry import (
    get_tool_metadata,
    list_tool_metadata,
    list_tools,
    register_tool,
)


def test_registry_lists_registered_tools():
    tools = list_tools()

    names = [tool.name for tool in tools]

    assert "calculator" in names
    assert "datetime" in names


def test_registry_returns_tool_metadata():
    metadata = get_tool_metadata("calculator")

    assert metadata is not None
    assert metadata["name"] == "calculator"
    assert metadata["description"]
    assert metadata["input_schema"]["type"] == "object"
    assert metadata["input_schema"]["required"] == ["expression"]
    assert "expression" in metadata["input_schema"]["properties"]
    assert (
        metadata["input_schema"]["properties"]["expression"]["type"]
        == "string"
    )
    assert metadata["input_schema"]["additionalProperties"] is False

def test_registry_lists_tool_metadata():
    metadata = list_tool_metadata()

    names = [item["name"] for item in metadata]

    assert "calculator" in names
    assert "datetime" in names


def test_registry_returns_none_for_unknown_metadata():
    metadata = get_tool_metadata("missing-tool")

    assert metadata is None


def test_registry_supports_dynamic_tool_registration():
    class EchoTool(BaseTool):
        name = "echo"
        description = "Echo the provided input."
        input_schema = {
            "type": "string",
        }

        def run(self, input_text: str):
            return input_text

    echo_tool = EchoTool()

    register_tool(echo_tool)

    registered_tool = get_tool("echo")

    assert registered_tool is echo_tool
    assert registered_tool.run("hello") == "hello"

    metadata = get_tool_metadata("echo")

    assert metadata is not None
    assert metadata["name"] == "echo"
    assert metadata["description"] == "Echo the provided input."
    assert metadata["input_schema"]["type"] == "string"

    names = [item["name"] for item in list_tool_metadata()]

    assert "echo" in names
