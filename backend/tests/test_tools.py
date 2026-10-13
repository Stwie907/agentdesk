import pytest

from app.runtime.executor import (
    ToolNotFoundError,
    execute_tool,
)
from app.tools.registry import get_tool


def test_calculator_registered():
    tool = get_tool("calculator")

    assert tool is not None
    assert tool.name == "calculator"


def test_datetime_registered():
    tool = get_tool("datetime")

    assert tool is not None
    assert tool.name == "datetime"


def test_calculator_execution():
    result = execute_tool(
        "calculator",
        "12345*6789",
    )

    assert result == "83810205"


def test_datetime_execution():
    result = execute_tool(
        "datetime",
        "",
    )

    assert isinstance(result, str)
    assert len(result) > 0


def test_unknown_tool():
    with pytest.raises(
        ToolNotFoundError,
        match="not_exists",
    ):
        execute_tool(
            "not_exists",
            "",
        )
