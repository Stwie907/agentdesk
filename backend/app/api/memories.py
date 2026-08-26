from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db

from app.schemas.memory import (
    MemoryCreate,
    MemoryResponse,
)

from app.crud.memory import (
    create_memory,
    get_memory,
    get_memories_by_agent,
    delete_memory,
)


router = APIRouter(
    prefix="/memories",
    tags=["memories"],
)


@router.post(
    "",
    response_model=MemoryResponse,
)
def create(
    memory: MemoryCreate,
    db: Session = Depends(get_db),
):
    return create_memory(
        db,
        memory,
    )


@router.get(
    "/{agent_id}",
    response_model=list[MemoryResponse],
)
def list_agent_memories(
    agent_id: int,
    db: Session = Depends(get_db),
):
    return get_memories_by_agent(
        db,
        agent_id,
    )


@router.delete(
    "/item/{memory_id}",
)
def remove(
    memory_id: int,
    db: Session = Depends(get_db),
):
    memory = delete_memory(
        db,
        memory_id,
    )

    if not memory:
        raise HTTPException(
            status_code=404,
            detail="Memory not found",
        )

    return {
        "message": "Memory deleted successfully"
    }
