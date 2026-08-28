from dataclasses import dataclass
from enum import Enum
from app.runtime.executor import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolPermissionDenied,
)
from app.tools.base import ToolArgumentsError

class FailureType(str, Enum):
    """
    Standard execution failure categories.
    """

    AGENT_NOT_FOUND = "agent_not_found"

    TOOL_NOT_FOUND = "tool_not_found"
    TOOL_PERMISSION_DENIED = "tool_permission_denied"
    TOOL_ARGUMENTS_ERROR = "tool_arguments_error"
    TOOL_EXECUTION_ERROR = "tool_execution_error"

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

    if isinstance(error, ToolNotFoundError):
        return ExecutionFailure(
            failure_type=FailureType.TOOL_NOT_FOUND,
            message=str(error),
            retryable=False,
        )

    if isinstance(error, ToolPermissionDenied):
        return ExecutionFailure(
            failure_type=FailureType.TOOL_PERMISSION_DENIED,
            message=str(error),
            retryable=False,
        )

    if isinstance(error, ToolArgumentsError):
        return ExecutionFailure(
            failure_type=FailureType.TOOL_ARGUMENTS_ERROR,
            message=str(error),
            retryable=False,
        )

    if isinstance(error, ToolExecutionError):
        return ExecutionFailure(
            failure_type=FailureType.TOOL_EXECUTION_ERROR,
            message=str(error),
            retryable=False,
        )


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
