import re
from enum import Enum

from sqlalchemy.orm import Session

from app.crud.execution_log import create_log
from app.models.execution_log import ExecutionLog


class TraceEvent(str, Enum):
    """
    Standard events emitted during one Agent execution.

    These events make the Agent runtime observable without changing
    the existing execution_logs database structure.
    """

    EXECUTION_STARTED = "execution_started"

    MEMORY_RETRIEVAL_STARTED = "memory_retrieval_started"
    MEMORY_RETRIEVED = "memory_retrieved"

    CONVERSATION_HISTORY_LOADED = "conversation_history_loaded"

    AGENT_STARTED = "agent_started"

    EXECUTION_COMPLETED = "execution_completed"
    EXECUTION_FAILED = "execution_failed"
    EXECUTION_RETRYING = "execution_retrying"

    PLANNER_DECISION = "planner_decision"

    PLAN_STARTED = "plan_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    PLAN_COMPLETED = "plan_completed"
    PLAN_FAILED = "plan_failed"

    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"

    LLM_CALLED = "llm_called"
    LLM_COMPLETED = "llm_completed"


RUNTIME_V4_TRACE_EVENTS = {
    TraceEvent.PLAN_STARTED.value,
    TraceEvent.STEP_STARTED.value,
    TraceEvent.STEP_COMPLETED.value,
    TraceEvent.STEP_FAILED.value,
    TraceEvent.PLAN_COMPLETED.value,
    TraceEvent.PLAN_FAILED.value,
}


def trace_event(
    db: Session,
    execution_id: int,
    event: TraceEvent,
    detail: str = "",
    level: str = "info",
):
    """
    Persist one structured execution trace event.

    The first version intentionally reuses ExecutionLog instead of
    introducing a new database table.

    Stored message format:

        event

        event: detail
    """

    message = event.value

    if detail:
        message = f"{event.value}: {detail}"

    return create_log(
        db,
        execution_id,
        message,
        level=level,
    )


def get_runtime_v4_trace(
    db: Session,
    execution_id: int,
) -> list[dict]:
    """
    Return structured Runtime V4 plan/step trace events.

    Runtime V4 trace data is currently persisted in ExecutionLog.message.
    This reader filters the existing log records and converts the internal
    message format into an API-friendly structured representation.

    Results remain ordered by ExecutionLog.id so clients receive events
    in the same order in which they were persisted.
    """

    logs = (
        db.query(ExecutionLog)
        .filter(ExecutionLog.execution_id == execution_id)
        .order_by(ExecutionLog.id)
        .all()
    )

    trace = []

    for log in logs:
        parsed = _parse_runtime_v4_trace_log(log)

        if parsed is not None:
            trace.append(parsed)

    return trace


def _parse_runtime_v4_trace_log(
    log: ExecutionLog,
) -> dict | None:
    """
    Convert one Runtime V4 ExecutionLog record into structured trace data.

    Supported examples:

        plan_started

        step_started: step=0 tool=calculator

        step_completed: step=0 tool=calculator

        step_failed: step=1 tool=calculator; error=calculator exploded

        plan_completed

        plan_failed: step=1; error=calculator exploded
    """

    message = log.message

    event = message.split(":", 1)[0].strip()

    if event not in RUNTIME_V4_TRACE_EVENTS:
        return None

    step_index = _parse_step_index(message)
    tool = _parse_tool(message)
    error = _parse_error(message)

    return {
        "id": log.id,
        "execution_id": log.execution_id,
        "event": event,
        "step_index": step_index,
        "tool": tool,
        "error": error,
        "message": log.message,
        "created_at": log.created_at,
    }


def _parse_step_index(message: str) -> int | None:
    """
    Extract a zero-based step index from a Runtime V4 trace message.
    """

    match = re.search(r"\bstep=(\d+)\b", message)

    if match is None:
        return None

    return int(match.group(1))


def _parse_tool(message: str) -> str | None:
    """
    Extract a tool name from a Runtime V4 trace message.

    Tool names are terminated by whitespace, semicolon, or end-of-string.
    """

    match = re.search(r"\btool=([^\s;]+)", message)

    if match is None:
        return None

    return match.group(1)


def _parse_error(message: str) -> str | None:
    """
    Extract failure information from a Runtime V4 trace message.

    Error text is intentionally allowed to contain spaces because runtime
    exceptions may contain human-readable messages.
    """

    marker = "error="

    if marker not in message:
        return None

    error = message.split(marker, 1)[1].strip()

    if not error:
        return None

    return error


def _is_runtime_v4_trace_message(message: str) -> bool:
    """
    Check whether an ExecutionLog message belongs to Runtime V4
    plan/step execution tracing.
    """

    event_name = message.split(":", 1)[0].strip()

    return event_name in RUNTIME_V4_TRACE_EVENTS
