from sqlalchemy.orm import Session
from collections.abc import Callable
from datetime import datetime, timezone
import os

from app.memory_config import get_memory_settings
from app.services.memory_embeddings import SemanticMemoryUnavailable, get_embedding_settings
from app.services.semantic_memory import rank_semantic_rows

from app.crud.memory import get_memories_by_agent
from app.schemas.memory import MemoryCreate
from app.crud.memory import create_memory
from app.services.memory_retrieval import MemoryMatch, rank_agent_memories, rank_memory_rows
from app.models.memory import Memory
from app.schemas.memory_evidence import MemoryEvidence, MemoryEvidenceItem, render_memory_context


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
    on_fallback: Callable[[str], None] | None = None,
    on_details: Callable[[MemoryEvidence], None] | None = None,
) -> str:
    """
    Build persistent memory context for the agent runtime.

    The returned text can be injected into the LLM prompt.
    """
    from app.services.user_memory_service import list_user_memories, owner_for_agent

    query = query.strip()
    limit = max(0, limit)
    owner = owner_for_agent(db, agent_id)
    requested_mode = "semantic" if os.getenv("MEMORY_RETRIEVAL_MODE", "keyword").strip().lower() == "semantic" else "keyword"
    fallback_reason = None
    settings = None
    try:
        mode = get_memory_settings().mode
    except ValueError as error:
        mode = "keyword"
        fallback_reason = str(error)
        if on_fallback is not None:
            on_fallback(fallback_reason)

    local = get_agent_memories(db, agent_id) if limit > 0 else []
    shared = [] if owner is None or limit == 0 else list_user_memories(db, owner.id)
    if mode == "semantic" and query and limit > 0:
        try:
            settings = get_embedding_settings()
            # Embed both sources together. Rank each scope afterward
            # so shared memories do not consume the Agent memory result budget.
            matches = rank_semantic_rows([*local, *shared], query, settings, len(local) + len(shared))
            agent_matches = [match for match in matches if isinstance(match.memory, Memory)][:limit]
            shared_matches = [match for match in matches if not isinstance(match.memory, Memory)][:limit]
        except SemanticMemoryUnavailable as error:
            mode = "keyword"
            fallback_reason = str(error)
            if on_fallback is not None:
                on_fallback(fallback_reason)
    else:
        # An empty query or zero budget never performs semantic retrieval.
        mode = "keyword"
    if mode == "keyword":
        agent_matches = rank_memory_rows(local, query, limit) if query else [MemoryMatch(row, 0, ()) for row in local[:limit]]
        shared_matches = rank_memory_rows(shared, query, limit) if query else [MemoryMatch(row, 0, ()) for row in shared[:limit]]

    def capture(matches, scope, scope_id):
        return [MemoryEvidenceItem(
            memory_id=match.memory.id, scope=scope, scope_id=scope_id,
            content=match.memory.content, created_at=match.memory.created_at,
            score=match.score if mode == "keyword" else None,
            matched_terms=list(match.matched_terms) if mode == "keyword" else [],
            similarity=match.similarity if mode == "semantic" else None,
        ) for match in matches]

    agent_items = capture(agent_matches, "agent", agent_id)
    shared_items = capture(shared_matches, "user", None if owner is None else owner.id)
    context = render_memory_context(agent_items, shared_items)
    if on_details is not None:
        on_details(MemoryEvidence(
            version=1, agent_id=agent_id, user_id=None if owner is None else owner.id,
            query=query, limit=limit, recorded_at=datetime.now(timezone.utc),
            requested_mode=requested_mode, mode=mode,
            provider=settings.provider if mode == "semantic" else None,
            model=settings.model if mode == "semantic" else None,
            min_similarity=settings.memory.min_similarity if mode == "semantic" else None,
            fallback_reason=fallback_reason, agent_memories=agent_items,
            shared_memories=shared_items, context=context,
        ))
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
