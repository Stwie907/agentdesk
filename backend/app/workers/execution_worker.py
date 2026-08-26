from app.database import SessionLocal

from app.constants import ExecutionStatus

from app.models.execution import Execution
from app.models.agent import Agent

from app.services.memory_service import build_memory_context
from app.services.agent_runner import run_agent
from app.services.execution_trace import TraceEvent, trace_event


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

        # ---------------------------------------------------------
        # Execution started
        # ---------------------------------------------------------

        execution.status = ExecutionStatus.RUNNING.value
        db.commit()

        trace_event(
            db,
            execution.id,
            TraceEvent.EXECUTION_STARTED,
        )

        # ---------------------------------------------------------
        # Load agent
        # ---------------------------------------------------------

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

        # ---------------------------------------------------------
        # Memory retrieval
        # ---------------------------------------------------------

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

        # ---------------------------------------------------------
        # Conversation history
        # ---------------------------------------------------------

        if conversation_history:
            trace_event(
                db,
                execution.id,
                TraceEvent.CONVERSATION_HISTORY_LOADED,
            )

        # ---------------------------------------------------------
        # Agent Runtime
        # ---------------------------------------------------------

        trace_event(
            db,
            execution.id,
            TraceEvent.AGENT_STARTED,
        )

        result = run_agent(
            agent.model,
            execution.input,
            memory_text,
            conversation_history,
            execution_id=execution.id,
        )

        # ---------------------------------------------------------
        # Execution completed
        # ---------------------------------------------------------

        execution.output = str(result)
        execution.status = ExecutionStatus.COMPLETED.value

        trace_event(
            db,
            execution.id,
            TraceEvent.EXECUTION_COMPLETED,
        )

        db.commit()

    except Exception as e:
        db.rollback()

        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        if execution:
            execution.output = str(e)
            execution.status = ExecutionStatus.FAILED.value

            trace_event(
                db,
                execution.id,
                TraceEvent.EXECUTION_FAILED,
                detail=str(e),
                level="error",
            )

            db.commit()

    finally:
        db.close()
