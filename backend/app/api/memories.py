from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.database import get_db

from app.schemas.memory import (
    MemoryCreateRequest,
    MemoryResponse,
)

from app.crud.agent import get_agent
from app.crud.memory import get_memory, get_memories_by_agent, delete_memory
from app.services.memory_service import save_agent_memory


router = APIRouter(
    prefix="/memories",
    tags=["memories"],
)


@router.post(
    "",
    response_model=MemoryResponse,
)
def create(
    memory: MemoryCreateRequest,
    db: Session = Depends(get_db),
):
    if get_agent(db, memory.agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return save_agent_memory(db, memory.agent_id, memory.content)


@router.get(
    "/{agent_id}",
    response_model=list[MemoryResponse],
)
def list_agent_memories(
    agent_id: Annotated[int, Path(gt=0)],
    db: Session = Depends(get_db),
):
    if get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    return get_memories_by_agent(
        db,
        agent_id,
    )


@router.delete(
    "/item/{memory_id}",
)
def remove(
    memory_id: Annotated[int, Path(gt=0)],
    db: Session = Depends(get_db),
    agent_id: Annotated[int | None, Query(gt=0)] = None,
):
    memory = get_memory(db, memory_id)

    if not memory:
        raise HTTPException(
            status_code=404,
            detail="Memory not found",
        )

    if agent_id is not None and memory.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Memory not found for this Agent")

    # Older clients can omit agent_id; the workbench always supplies its scope.
    delete_memory(db, memory_id)

    return {
        "message": "Memory deleted successfully"
    }
