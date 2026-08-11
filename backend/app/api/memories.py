from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryResponse


router = APIRouter(
    prefix="/memories",
    tags=["memories"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



@router.post(
    "",
    response_model=MemoryResponse
)
def create_memory(
    memory: MemoryCreate,
    db: Session = Depends(get_db)
):

    new_memory = Memory(
        agent_id=memory.agent_id,
        content=memory.content
    )

    db.add(new_memory)
    db.commit()
    db.refresh(new_memory)

    return new_memory



@router.get(
    "/{agent_id}",
    response_model=list[MemoryResponse]
)
def get_memories(
    agent_id: int,
    db: Session = Depends(get_db)
):

    return (
        db.query(Memory)
        .filter(
            Memory.agent_id == agent_id
        )
        .all()
    )

