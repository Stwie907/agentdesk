import pytest

from app.runtime.executor import (
    ToolPermissionDenied,
    execute_tool,
)


def test_execute_allowed_tool():
    result = execute_tool(
        "calculator",
        "1+1",
        allowed_tools=["calculator"],
    )

    assert str(result) == "2"


def test_execute_denied_tool():
    with pytest.raises(
        ToolPermissionDenied,
        match="datetime",
    ):
        execute_tool(
            "datetime",
            "",
            allowed_tools=["calculator"],
        )


def test_empty_allowed_tools_denies_tool():
    with pytest.raises(ToolPermissionDenied):
        execute_tool(
            "calculator",
            "1+1",
            allowed_tools=[],
        )


def test_none_allowed_tools_keeps_backward_compatibility():
    result = execute_tool(
        "calculator",
        "2+3",
    )

    assert str(result) == "5"


def test_unknown_tool_without_permission_restriction():
    result = execute_tool(
        "unknown-tool",
        "",
    )

    assert result == "Tool not found"
