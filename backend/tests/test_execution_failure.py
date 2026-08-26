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
