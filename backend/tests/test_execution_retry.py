from app.services.execution_failure import (
    ExecutionFailure,
    FailureType,
)

from app.services.execution_retry import (
    RetryPolicy,
    should_retry,
)


def test_retryable_failure_can_retry():
    failure = ExecutionFailure(
        failure_type=FailureType.TIMEOUT,
        message="request timed out",
        retryable=True,
    )

    policy = RetryPolicy(
        max_retries=2,
    )

    assert should_retry(
        failure,
        retry_count=0,
        policy=policy,
    ) is True


def test_retryable_failure_can_retry_second_time():
    failure = ExecutionFailure(
        failure_type=FailureType.CONNECTION_ERROR,
        message="connection refused",
        retryable=True,
    )

    policy = RetryPolicy(
        max_retries=2,
    )

    assert should_retry(
        failure,
        retry_count=1,
        policy=policy,
    ) is True


def test_retryable_failure_stops_after_limit():
    failure = ExecutionFailure(
        failure_type=FailureType.TIMEOUT,
        message="request timed out",
        retryable=True,
    )

    policy = RetryPolicy(
        max_retries=2,
    )

    assert should_retry(
        failure,
        retry_count=2,
        policy=policy,
    ) is False


def test_non_retryable_failure_never_retries():
    failure = ExecutionFailure(
        failure_type=FailureType.RUNTIME_ERROR,
        message="runtime failed",
        retryable=False,
    )

    policy = RetryPolicy(
        max_retries=2,
    )

    assert should_retry(
        failure,
        retry_count=0,
        policy=policy,
    ) is False
