from sqlalchemy.orm import Session

from app.crud.memory import get_memories_by_agent
from app.schemas.memory import MemoryCreate
from app.crud.memory import create_memory
from app.services.memory_retrieval import rank_agent_memories


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

def retrieve_relevant_memories(
    db: Session,
    agent_id: int,
    query: str,
    limit: int = 5,
):
    """Use the same deterministic ranking as the workbench preview."""
    if limit <= 0:
        return []
    # Preserve the existing empty-query context behavior for internal callers.
    if not query.strip():
        return get_agent_memories(db, agent_id)[:limit]
    return [match.memory for match in rank_agent_memories(db, agent_id, query, limit)]


def build_memory_context(
    db: Session,
    agent_id: int,
    query: str = "",
    limit: int = 5,
) -> str:
    """
    Build persistent memory context for the agent runtime.

    The returned text can be injected into the LLM prompt.
    """
    memories = retrieve_relevant_memories(
        db,
        agent_id,
        query,
        limit,
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
