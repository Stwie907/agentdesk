from sqlalchemy.orm import Session

from app.models.memory import Memory
from app.schemas.memory import MemoryCreate
from app.services.memory_vector_cache import invalidate_memory_vectors


def create_memory(
    db: Session,
    memory: MemoryCreate,
):
    db_memory = Memory(
        agent_id=memory.agent_id,
        content=memory.content,
    )

    db.add(db_memory)
    db.commit()
    db.refresh(db_memory)

    return db_memory


def get_memory(
    db: Session,
    memory_id: int,
):
    return (
        db.query(Memory)
        .filter(Memory.id == memory_id)
        .first()
    )


def get_memories_by_agent(
    db: Session,
    agent_id: int,
):
    return (
        db.query(Memory)
        .filter(Memory.agent_id == agent_id)
        .order_by(Memory.created_at.asc(), Memory.id.asc())
        .all()
    )


def delete_memory(
    db: Session,
    memory_id: int,
):
    memory = get_memory(
        db,
        memory_id,
    )

    if not memory:
        return None

    try:
        invalidate_memory_vectors(db, "agent", memory.agent_id, memory.id)
        db.delete(memory)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return memory
