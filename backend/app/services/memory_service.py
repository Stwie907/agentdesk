from sqlalchemy.orm import Session

from app.crud.memory import get_memories_by_agent
from app.schemas.memory import MemoryCreate
from app.crud.memory import create_memory
from app.services.memory_retrieval import rank_agent_memories
from app.models.memory import Memory


class MemoryEditConflict(ValueError):
    """An edit conflicts with the current record or another saved memory."""


def update_agent_memory(db: Session, memory: Memory, content: str, expected_content: str):
    """Edit one row with a conditional write, retaining its identity and time."""
    normalized = content.strip()
    if memory.content != expected_content:
        raise MemoryEditConflict("Memory changed since it was loaded. Reload memories before editing again.")
    for other in get_memories_by_agent(db, memory.agent_id):
        if other.id == memory.id:
            continue
        if other.content.strip() == normalized:
            raise MemoryEditConflict("An identical memory already exists for this Agent. Use different content.")
        if normalized.startswith("User's name is ") and other.content.strip().startswith("User's name is "):
            raise MemoryEditConflict("A name memory already exists for this Agent. Edit that memory instead.")
    try:
        # Checking the original content in SQL also protects the interval after
        # the read, including automatic name replacement by a chat request.
        changed = db.query(Memory).filter(
            Memory.id == memory.id,
            Memory.agent_id == memory.agent_id,
            Memory.content == expected_content,
        ).update({Memory.content: normalized}, synchronize_session=False)
        if changed != 1:
            raise MemoryEditConflict("Memory changed since it was loaded. Reload memories before editing again.")
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(memory)
    return memory


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

    agent_context = "\n".join(
        memory.content
        for memory in memories
    )
    from app.services.user_memory_service import user_memory_context
    shared_context = user_memory_context(db, agent_id, query, limit)
    if not shared_context:
        return agent_context
    context = "Shared user memory:\n" + shared_context
    if agent_context:
        context += "\nAgent memory:\n" + agent_context
    return context


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
