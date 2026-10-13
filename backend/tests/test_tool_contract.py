from app.runtime.executor import execute_tool


def test_calculator_accepts_structured_arguments():
    """
    Calculator should eventually accept structured arguments
    instead of a raw string.
    """
    result = execute_tool(
        "calculator",
        {
            "expression": "12345*6789",
        },
    )

    assert result == "83810205"


def test_datetime_accepts_structured_arguments():
    """
    Datetime should accept a structured argument object.
    """
    result = execute_tool(
        "datetime",
        {},
    )

    assert isinstance(result, str)
    assert result != ""


def test_calculator_rejects_missing_expression():
    """
    Missing required calculator arguments should fail predictably.
    """
    try:
        execute_tool(
            "calculator",
            {},
        )
    except (ValueError, TypeError):
        return

    raise AssertionError(
        "calculator should reject missing expression"
    )


def test_calculator_rejects_invalid_argument_name():
    """
    Unknown structured arguments should not silently pass through.
    """
    try:
        execute_tool(
            "calculator",
            {
                "wrong_field": "1+1",
            },
        )
    except (ValueError, TypeError):
        return

    raise AssertionError(
        "calculator should reject unknown arguments"
    )


def test_structured_arguments_still_enforce_permissions():
    """
    Structured arguments must not bypass Agent tool permissions.
    """
    try:
        execute_tool(
            "calculator",
            {
                "expression": "1+1",
            },
            allowed_tools=["datetime"],
        )
    except Exception as exc:
        assert exc.__class__.__name__ == "ToolPermissionDenied"
        return

    raise AssertionError(
        "unauthorized structured tool execution should be denied"
    )


def test_executor_supports_structured_arguments_for_registered_tool():
    from app.tools.base import BaseTool
    from app.tools.registry import register_tool

    class EchoStructuredTool(BaseTool):
        name = "echo_structured"
        description = "Echo a structured message."
        input_schema = {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                },
            },
            "required": ["message"],
            "additionalProperties": False,
        }

        def run(self, arguments):
            return arguments["message"]

    register_tool(EchoStructuredTool())

    result = execute_tool(
        "echo_structured",
        {
            "message": "hello",
        },
    )

    assert result == "hello"
