from dataclasses import dataclass

from app.services.execution_failure import ExecutionFailure


@dataclass(frozen=True)
class RetryPolicy:
    """
    Retry policy for Agent executions.
    """

    max_retries: int = 2


DEFAULT_RETRY_POLICY = RetryPolicy(
    max_retries=2,
)


def should_retry(
    failure: ExecutionFailure,
    retry_count: int,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
) -> bool:
    """
    Decide whether an execution failure should be retried.

    retry_count means how many retries have already happened.

    Example with max_retries=2:

        retry_count=0 -> first retry allowed
        retry_count=1 -> second retry allowed
        retry_count=2 -> no more retry
    """

    if not failure.retryable:
        return False

    return retry_count < policy.max_retries
