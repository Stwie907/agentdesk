from sqlalchemy.orm import Session

from app.crud.memory import get_memories_by_agent
from app.schemas.memory import MemoryCreate
from app.crud.memory import create_memory


def get_agent_memories(
    db: Session,
    agent_id: int,
):
    """
    Return all persistent memories belonging to an agent.
    """
    return get_memories_by_agent(
        db,
        agent_id,
    )


def build_memory_context(
    db: Session,
    agent_id: int,
) -> str:
    """
    Build persistent memory context for the agent runtime.

    The returned text can be injected into the LLM prompt.
    """
    memories = get_agent_memories(
        db,
        agent_id,
    )

    if not memories:
        return ""

    return "\n".join(
        memory.content
        for memory in memories
    )


def save_agent_memory(
    db: Session,
    agent_id: int,
    content: str,
):
    """
    Save one persistent memory for an agent.

    Behavior:
    - ignore empty memories
    - reuse exact duplicates
    - replace conflicting name memories
    """

    normalized_content = content.strip()

    if not normalized_content:
        return None

    existing_memories = get_agent_memories(
        db,
        agent_id,
    )

    # 1. Exact duplicate
    for memory in existing_memories:
        if memory.content.strip() == normalized_content:
            return memory

    # 2. Replace old name memory
    if normalized_content.startswith("User's name is "):
        for memory in existing_memories:
            if memory.content.strip().startswith("User's name is "):
                memory.content = normalized_content
                db.commit()
                db.refresh(memory)

                return memory

    # 3. Otherwise create a new memory
    return create_memory(
        db,
        MemoryCreate(
            agent_id=agent_id,
            content=normalized_content,
        ),
    )
