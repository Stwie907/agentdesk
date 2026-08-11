from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.execution import ExecutionCreate, ExecutionRead
from app.crud.execution import (
    create_execution,
    get_execution
)

from fastapi import BackgroundTasks
from app.workers.execution_worker import execute_agent
from app.models.agent import Agent

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

    return get_execution(
        db,
        execution_id
    )
