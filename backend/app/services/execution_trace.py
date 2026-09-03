from enum import Enum

from sqlalchemy.orm import Session

from app.crud.execution_log import create_log


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
    PLAN_COMPLETED = "plan_completed"

    TOOL_CALLED = "tool_called"
    TOOL_RESULT = "tool_result"

    LLM_CALLED = "llm_called"
    LLM_COMPLETED = "llm_completed"

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
