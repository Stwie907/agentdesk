from dataclasses import dataclass
from enum import Enum


class FailureType(str, Enum):
    """
    Standard execution failure categories.
    """

    AGENT_NOT_FOUND = "agent_not_found"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    RUNTIME_ERROR = "runtime_error"
    UNKNOWN_ERROR = "unknown_error"


@dataclass(frozen=True)
class ExecutionFailure:
    """
    Structured representation of an execution failure.
    """

    failure_type: FailureType
    message: str
    retryable: bool


def classify_failure(error: Exception) -> ExecutionFailure:
    """
    Convert a runtime exception into a structured execution failure.

    Retry policy belongs here so the worker does not need to know
    the details of individual exception types.
    """

    if isinstance(error, TimeoutError):
        return ExecutionFailure(
            failure_type=FailureType.TIMEOUT,
            message=str(error),
            retryable=True,
        )

    if isinstance(error, ConnectionError):
        return ExecutionFailure(
            failure_type=FailureType.CONNECTION_ERROR,
            message=str(error),
            retryable=True,
        )

    if isinstance(error, RuntimeError):
        return ExecutionFailure(
            failure_type=FailureType.RUNTIME_ERROR,
            message=str(error),
            retryable=False,
        )

    return ExecutionFailure(
        failure_type=FailureType.UNKNOWN_ERROR,
        message=str(error),
        retryable=False,
    )
