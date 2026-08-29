from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas.agent import AgentCreate, AgentResponse
from app.schemas.execution import ExecutionCreate, ExecutionRead
from app.schemas.chat import ChatRequest, ChatResponse
from app.workers.execution_worker import execute_agent
from app.crud.execution import (
    create_execution,
    get_executions_by_agent,
)

from app.crud.agent import (
    create_agent,
    get_agent,
    get_agents,
    delete_agent
)

router = APIRouter()


@router.post(
    "/agents",
    response_model=AgentResponse
)
def create(
    agent: AgentCreate,
    db: Session = Depends(get_db)
):

    return create_agent(db, agent)



@router.get(
    "/agents/{agent_id}",
    response_model=AgentResponse
)
def read(
    agent_id:int,
    db:Session=Depends(get_db)
):

    return get_agent(db, agent_id)


@router.get(
    "/agents",
    response_model=list[AgentResponse]
)
def read_agents(
    db: Session = Depends(get_db)
):

    return get_agents(db)

@router.delete(
    "/agents/{agent_id}"
)
def delete(
    agent_id:int,
    db:Session=Depends(get_db)
):

    agent = delete_agent(db, agent_id)

    if not agent:
        return {
            "message": "Agent not found"
        }

    return {
        "message": "Agent deleted successfully"
    }


@router.get(
    "/agents/{agent_id}/executions",
    response_model=list[ExecutionRead]
)
def read_agent_executions(
    agent_id: int,
    db: Session = Depends(get_db)
):
    agent = get_agent(db, agent_id)

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found",
        )

    return get_executions_by_agent(db, agent_id)

@router.post(
    "/agents/{agent_id}/chat",
    response_model=ChatResponse
)
def chat_with_agent(
    agent_id: int,
    chat: ChatRequest,
    db: Session = Depends(get_db)
):
    agent = get_agent(db, agent_id)

    if not agent:
        raise HTTPException(
            status_code=404,
            detail="Agent not found"
        )

    execution = create_execution(
        db,
        ExecutionCreate(
            agent_id=agent_id,
            input=chat.message,
        )
    )

    execute_agent(execution.id)

    db.refresh(execution)

    return ChatResponse(
        execution_id=execution.id,
        response=execution.output or "",
        status=execution.status,
    )
