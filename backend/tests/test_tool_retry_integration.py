from app.runtime.executor import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionDenied,
)
from app.services.execution_failure import (
    FailureType,
    classify_failure,
)
from app.services.execution_retry import should_retry
from app.tools.base import ToolArgumentsError


def test_tool_not_found_is_not_retryable():
    failure = classify_failure(
        ToolNotFoundError("missing_tool")
    )

    assert failure.failure_type == FailureType.TOOL_NOT_FOUND
    assert failure.retryable is False
    assert should_retry(failure, retry_count=0) is False


def test_tool_permission_denied_is_not_retryable():
    failure = classify_failure(
        ToolPermissionDenied("calculator")
    )

    assert (
        failure.failure_type
        == FailureType.TOOL_PERMISSION_DENIED
    )
    assert failure.retryable is False
    assert should_retry(failure, retry_count=0) is False


def test_tool_arguments_error_is_not_retryable():
    failure = classify_failure(
        ToolArgumentsError("invalid arguments")
    )

    assert (
        failure.failure_type
        == FailureType.TOOL_ARGUMENTS_ERROR
    )
    assert failure.retryable is False
    assert should_retry(failure, retry_count=0) is False


def test_tool_execution_error_is_not_retryable():
    failure = classify_failure(
        ToolExecutionError(
            "calculator",
            RuntimeError("boom"),
        )
    )

    assert (
        failure.failure_type
        == FailureType.TOOL_EXECUTION_ERROR
    )
    assert failure.retryable is False
    assert should_retry(failure, retry_count=0) is False


def test_timeout_is_retryable_until_limit():
    failure = classify_failure(
        TimeoutError("tool timed out")
    )

    assert failure.failure_type == FailureType.TIMEOUT
    assert failure.retryable is True

    assert should_retry(failure, retry_count=0) is True
    assert should_retry(failure, retry_count=1) is True
    assert should_retry(failure, retry_count=2) is False


def test_connection_error_is_retryable_until_limit():
    failure = classify_failure(
        ConnectionError("connection refused")
    )

    assert (
        failure.failure_type
        == FailureType.CONNECTION_ERROR
    )
    assert failure.retryable is True

    assert should_retry(failure, retry_count=0) is True
    assert should_retry(failure, retry_count=1) is True
    assert should_retry(failure, retry_count=2) is False
