from app.database import SessionLocal

from app.constants import ExecutionStatus

from app.models.execution import Execution
from app.models.agent import Agent
from app.models.memory import Memory

from app.services.agent_runner import run_agent

from app.crud.execution_log import create_log


def execute_agent(execution_id: int):
    db = SessionLocal()

    try:
        execution = (
            db.query(Execution)
            .filter(Execution.id == execution_id)
            .first()
        )

        if not execution:
            return

        execution.status = ExecutionStatus.RUNNING.value
        db.commit()

        create_log(
            db,
            execution.id,
            "Execution started",
        )

        agent = (
            db.query(Agent)
            .filter(Agent.id == execution.agent_id)
            .first()
        )

        if not agent:
            execution.status = ExecutionStatus.FAILED.value
            execution.output = "Agent not found"

            create_log(
                db,
                execution.id,
                "Agent not found",
            )

            db.commit()
            return

        create_log(
            db,
            execution.id,
            "Loading memory",
        )

        memories = (
            db.query(Memory)
            .filter(Memory.agent_id == agent.id)
            .all()
        )

        memory_text = "\n".join(
            memory.content
            for memory in memories
        )

        create_log(
            db,
            execution.id,
            "Running agent",
        )

        result = run_agent(
            agent.model,
            execution.input,
            memory_text,
        )

        execution.output = str(result)
        execution.status = ExecutionStatus.COMPLETED.value

        create_log(
            db,
            execution.id,
            "Execution completed",
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

            create_log(
                db,
                execution.id,
                str(e),
            )

            db.commit()

    finally:
        db.close()
