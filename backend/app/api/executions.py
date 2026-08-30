from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.execution import (
    ExecutionCreate,
    ExecutionRead,
    ExecutionLogRead,
)
from app.crud.execution import (
    create_execution,
    get_execution
)

from fastapi import BackgroundTasks
from app.workers.execution_worker import execute_agent
from app.models.agent import Agent
from app.crud.execution_log import get_logs

router = APIRouter(
    prefix="/executions",
    tags=["executions"]
)


@router.post(
    "",
    response_model=ExecutionRead
)
def create(
    execution: ExecutionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    agent = db.query(Agent).filter(
        Agent.id == execution.agent_id
    ).first()

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    db_execution = create_execution(
        db,
        execution
    )

    background_tasks.add_task(
        execute_agent,
        db_execution.id
    )


    return db_execution


@router.get(
    "/{execution_id}",
    response_model=ExecutionRead
)

def read(
    execution_id: int,
    db: Session = Depends(get_db)
):
    execution = get_execution(
        db,
        execution_id
    )

    if not execution:
        raise HTTPException(
            status_code=404,
            detail="Execution not found"
        )

    return execution

@router.get(
    "/{execution_id}/logs",
    response_model=list[ExecutionLogRead],
)
def read_execution_logs(
    execution_id: int,
    db: Session = Depends(get_db),
):
    execution = get_execution(
        db,
        execution_id,
    )

    if not execution:
        raise HTTPException(
            status_code=404,
            detail="Execution not found",
        )

    return get_logs(
        db,
        execution_id,
    )


@router.post(
    "/{execution_id}/retry",
    response_model=ExecutionRead,
)
def retry_execution(
    execution_id: int,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    execution = get_execution(
        db,
        execution_id,
    )

    if not execution:
        raise HTTPException(
            status_code=404,
            detail="Execution not found",
        )

    if execution.status != "failed":
        raise HTTPException(
            status_code=409,
            detail="Only failed executions can be retried",
        )

    # Reset runtime state for a fresh execution attempt.
    execution.status = "pending"
    execution.output = None

    # retry_count represents automatic retries within one worker run,
    # so a manual retry starts a new run from zero.
    execution.retry_count = 0

    # Previous failure metadata must not leak into the new run.
    execution.failure_type = None
    execution.failure_message = None

    db.commit()
    db.refresh(execution)

    background_tasks.add_task(
        execute_agent,
        execution.id,
    )

    return execution
