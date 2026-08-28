import pytest

from app.runtime.executor import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionDenied,
    execute_tool,
)
from app.tools.base import BaseTool, ToolArgumentsError
from app.tools.registry import register_tool


def test_unknown_tool_raises_tool_not_found_error():
    with pytest.raises(
        ToolNotFoundError,
        match="missing-tool",
    ):
        execute_tool(
            "missing-tool",
            "",
        )


def test_disallowed_tool_raises_permission_error():
    with pytest.raises(
        ToolPermissionDenied,
        match="datetime",
    ):
        execute_tool(
            "datetime",
            "",
            allowed_tools=["calculator"],
        )


def test_invalid_arguments_preserve_tool_arguments_error():
    with pytest.raises(ToolArgumentsError):
        execute_tool(
            "calculator",
            {},
        )


def test_tool_runtime_failure_becomes_tool_execution_error():
    class BrokenTool(BaseTool):
        name = "broken_test_tool"
        description = "Tool used to test runtime failure handling."
        input_schema = {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }

        def run(self, arguments):
            raise RuntimeError("boom")

    register_tool(BrokenTool())

    with pytest.raises(
        ToolExecutionError,
        match="boom",
    ):
        execute_tool(
            "broken_test_tool",
            {},
        )
