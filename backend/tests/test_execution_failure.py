from app.runtime.executor import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionDenied,
)
from app.tools.base import ToolArgumentsError

from app.services.execution_failure import (
    FailureType,
    classify_failure,
)


def test_timeout_failure_is_retryable():
    failure = classify_failure(
        TimeoutError("request timed out")
    )

    assert failure.failure_type == FailureType.TIMEOUT
    assert failure.message == "request timed out"
    assert failure.retryable is True


def test_connection_failure_is_retryable():
    failure = classify_failure(
        ConnectionError("connection refused")
    )

    assert failure.failure_type == FailureType.CONNECTION_ERROR
    assert failure.message == "connection refused"
    assert failure.retryable is True


def test_runtime_failure_is_not_retryable():
    failure = classify_failure(
        RuntimeError("runtime failed")
    )

    assert failure.failure_type == FailureType.RUNTIME_ERROR
    assert failure.message == "runtime failed"
    assert failure.retryable is False


def test_unknown_failure_is_not_retryable():
    failure = classify_failure(
        ValueError("invalid value")
    )

    assert failure.failure_type == FailureType.UNKNOWN_ERROR
    assert failure.message == "invalid value"
    assert failure.retryable is False


def test_tool_not_found_failure_is_not_retryable():
    failure = classify_failure(
        ToolNotFoundError("missing-tool")
    )

    assert failure.failure_type == FailureType.TOOL_NOT_FOUND
    assert "missing-tool" in failure.message
    assert failure.retryable is False


def test_tool_permission_failure_is_not_retryable():
    failure = classify_failure(
        ToolPermissionDenied("datetime")
    )

    assert (
        failure.failure_type
        == FailureType.TOOL_PERMISSION_DENIED
    )
    assert "datetime" in failure.message
    assert failure.retryable is False


def test_tool_arguments_failure_is_not_retryable():
    failure = classify_failure(
        ToolArgumentsError("missing required argument")
    )

    assert (
        failure.failure_type
        == FailureType.TOOL_ARGUMENTS_ERROR
    )
    assert "missing required argument" in failure.message
    assert failure.retryable is False


def test_tool_execution_failure_is_not_retryable():
    failure = classify_failure(
        ToolExecutionError(
            "broken-tool",
            "boom",
        )
    )

    assert (
        failure.failure_type
        == FailureType.TOOL_EXECUTION_ERROR
    )
    assert "boom" in failure.message
    assert failure.retryable is False
