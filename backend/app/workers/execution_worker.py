import json
from app.database import SessionLocal

from app.constants import ExecutionStatus

from app.models.execution import Execution
from app.models.agent import Agent

from app.services.memory_service import build_memory_context
from app.services.agent_runner import run_agent
from app.services.execution_trace import TraceEvent, trace_event
from app.services.execution_failure import classify_failure
from app.services.execution_retry import should_retry


def execute_agent(
    execution_id: int,
    conversation_history: str = "",
):
    db = SessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        if not execution:
            return

        # A cancelled execution must never be started by the worker.
        if execution.status == ExecutionStatus.CANCELLED.value:
            return
        # --------------------------------------------------------
        # Execution started
        # --------------------------------------------------------
        execution.status = ExecutionStatus.RUNNING.value
        db.commit()

        trace_event(
            db,
            execution.id,
            TraceEvent.EXECUTION_STARTED,
        )

        # --------------------------------------------------------
        # Load agent
        # --------------------------------------------------------
        agent = (
            db.query(Agent)
            .filter(Agent.id == execution.agent_id)
            .first()
        )

        if not agent:
            execution.status = ExecutionStatus.FAILED.value
            execution.output = "Agent not found"

            trace_event(
                db,
                execution.id,
                TraceEvent.EXECUTION_FAILED,
                detail="Agent not found",
                level="error",
            )

            db.commit()
            return

        # --------------------------------------------------------
        # Load Agent tool permissions
        # --------------------------------------------------------
        try:
            allowed_tools = json.loads(agent.allowed_tools)

            if not isinstance(allowed_tools, list):
                allowed_tools = ["calculator", "datetime"]

        except (json.JSONDecodeError, TypeError):
            allowed_tools = ["calculator", "datetime"]

        # --------------------------------------------------------
        # Memory retrieval
        # --------------------------------------------------------
        trace_event(
            db,
            execution.id,
            TraceEvent.MEMORY_RETRIEVAL_STARTED,
        )

        memory_text = build_memory_context(
            db,
            agent.id,
            execution.input,
        )

        trace_event(
            db,
            execution.id,
            TraceEvent.MEMORY_RETRIEVED,
            detail=(
                "Relevant memory loaded"
                if memory_text
                else "No relevant memory found"
            ),
        )

        # --------------------------------------------------------
        # Conversation history
        # --------------------------------------------------------
        if conversation_history:
            trace_event(
                db,
                execution.id,
                TraceEvent.CONVERSATION_HISTORY_LOADED,
            )

        # --------------------------------------------------------
        # Agent Runtime
        # --------------------------------------------------------
        trace_event(
            db,
            execution.id,
            TraceEvent.AGENT_STARTED,
        )

        retry_count = 0

        while True:
            try:
                result = run_agent(
                    agent.model,
                    execution.input,
                    memory_text,
                    conversation_history,
                    execution_id=execution.id,
                    allowed_tools=allowed_tools,
               )

                execution.output = str(result)
                execution.status = ExecutionStatus.COMPLETED.value

                # Persist retry metadata.
                execution.retry_count = retry_count

                # A successful final execution must not expose stale failure metadata.
                execution.failure_type = None
                execution.failure_message = None

                trace_event(
                    db,
                    execution.id,
                    TraceEvent.EXECUTION_COMPLETED,
                )

                db.commit()
                return

            except Exception as e:
                db.rollback()

                failure = classify_failure(e)

                if should_retry(
                    failure,
                    retry_count,
                ):
                    retry_count += 1

                    trace_event(
                        db,
                        execution.id,
                        TraceEvent.EXECUTION_RETRYING,
                        detail=(
                            f"attempt={retry_count}; "
                            f"type={failure.failure_type.value}; "
                            f"message={failure.message}"
                        ),
                        level="warning",
                    )

                    continue

                execution = (
                    db.query(Execution)
                    .filter(Execution.id == execution_id)
                    .first()
                )

                if execution:
                    execution.output = failure.message
                    execution.status = ExecutionStatus.FAILED.value

                    # Persist final retry/failure metadata.
                    execution.retry_count = retry_count
                    execution.failure_type = failure.failure_type.value
                    execution.failure_message = failure.message

                    trace_event(
                        db,
                        execution.id,
                        TraceEvent.EXECUTION_FAILED,
                        detail=(
                            f"type={failure.failure_type.value}; "
                            f"retryable={str(failure.retryable).lower()}; "
                            f"retries={retry_count}; "
                            f"message={failure.message}"
                        ),
                        level="error",
                    )

                    db.commit()

                return

    finally:
        db.close()
