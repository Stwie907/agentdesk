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

def retrieve_relevant_memories(
    db: Session,
    agent_id: int,
    query: str,
    limit: int = 5,
):
    """
    Retrieve memories relevant to the current user query.

    This lightweight retrieval implementation uses keyword
    overlap while ignoring common stop words.

    It is deterministic and does not require embeddings.
    """

    memories = get_agent_memories(
        db,
        agent_id,
    )

    if not memories:
        return []

    normalized_query = query.lower().strip()

    if not normalized_query:
        return memories[:limit]

    stop_words = {
        "a",
        "an",
        "the",
        "is",
        "are",
        "am",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "what",
        "which",
        "who",
        "whom",
        "where",
        "when",
        "why",
        "how",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "from",
        "with",
        "about",
        "and",
        "or",
    }

    def tokenize(text: str) -> set[str]:
        tokens = set()

        for token in text.lower().split():
            cleaned = token.strip(
                ".,!?;:'\"()[]{}"
            )

            if (
                cleaned
                and cleaned not in stop_words
            ):
                tokens.add(cleaned)

        return tokens

    query_tokens = tokenize(
        normalized_query
    )

    if not query_tokens:
        return []

    scored_memories = []

    for memory in memories:
        content_tokens = tokenize(
            memory.content
        )

        score = len(
            query_tokens & content_tokens
        )

        if score > 0:
            scored_memories.append(
                (
                    score,
                    memory,
                )
            )

    scored_memories.sort(
        key=lambda item: (
            item[0],
            item[1].id,
        ),
        reverse=True,
    )

    return [
        memory
        for _, memory in scored_memories[:limit]
    ]


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
