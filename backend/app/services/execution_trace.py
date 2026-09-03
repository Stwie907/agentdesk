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
) -> list[ExecutionLog]:
    """
    Return Runtime V4 plan/step trace events for one execution.

    Runtime V4 trace data is currently persisted in ExecutionLog.message,
    so this reader intentionally filters the existing log records instead
    of introducing a second persistence model.

    Results are ordered by ExecutionLog.id so API clients receive events
    in the same order in which they were persisted.
    """

    logs = (
        db.query(ExecutionLog)
        .filter(ExecutionLog.execution_id == execution_id)
        .order_by(ExecutionLog.id)
        .all()
    )

    return [
        log
        for log in logs
        if _is_runtime_v4_trace_message(log.message)
    ]


def _is_runtime_v4_trace_message(message: str) -> bool:
    """
    Check whether an ExecutionLog message belongs to Runtime V4
    plan/step execution tracing.
    """

    event_name = message.split(":", 1)[0].strip()

    return event_name in RUNTIME_V4_TRACE_EVENTS
