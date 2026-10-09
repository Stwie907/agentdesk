from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.database import get_db

from app.schemas.memory import (
    MemoryCreateRequest,
    MemoryResponse,
    MemorySearchResponse,
    MemorySearchResult,
    MemoryUpdateRequest,
)

from app.crud.agent import get_agent
from app.crud.memory import get_memory, get_memories_by_agent, delete_memory
from app.services.memory_service import MemoryEditConflict, save_agent_memory, update_agent_memory
from app.services.memory_retrieval import rank_agent_memories
from app.schemas.semantic_memory import SemanticMemoryResult, SemanticSearchResponse
from app.services.memory_embeddings import SemanticMemoryUnavailable, get_embedding_settings
from app.services.semantic_memory import rank_semantic_rows


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


@router.get("/{agent_id}/search", response_model=MemorySearchResponse)
def search_agent_memories(
    agent_id: Annotated[int, Path(gt=0)],
    query: Annotated[str, Query(min_length=1, max_length=500)],
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
):
    normalized_query = query.strip()
    if not normalized_query:
        raise HTTPException(status_code=422, detail="Enter a non-blank memory query")
    if get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    matches = rank_agent_memories(db, agent_id, normalized_query, limit)
    return MemorySearchResponse(
        agent_id=agent_id, query=normalized_query, limit=limit,
        results=[MemorySearchResult(memory=MemoryResponse.model_validate(match.memory),
                                   score=match.score, matched_terms=list(match.matched_terms)) for match in matches],
    )


@router.get("/{agent_id}/semantic-search", response_model=SemanticSearchResponse)
def search_agent_memories_semantically(
    agent_id: Annotated[int, Path(gt=0)],
    query: Annotated[str, Query(min_length=1, max_length=500)],
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    min_similarity: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
):
    normalized = query.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Enter a non-blank semantic memory query")
    if get_agent(db, agent_id) is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    rows = get_memories_by_agent(db, agent_id)
    try:
        settings = get_embedding_settings()
        minimum = settings.memory.min_similarity if min_similarity is None else min_similarity
        matches = rank_semantic_rows(rows, normalized, settings, limit, minimum)
    except SemanticMemoryUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return SemanticSearchResponse(agent_id=agent_id, query=normalized, limit=limit,
        provider=settings.provider, model=settings.model, runtime_mode=settings.memory.mode,
        min_similarity=minimum, results=[SemanticMemoryResult(memory=MemoryResponse.model_validate(match.memory),
                                                              similarity=match.similarity) for match in matches])


@router.patch("/item/{memory_id}", response_model=MemoryResponse)
def update(
    memory_id: Annotated[int, Path(gt=0)],
    memory: MemoryUpdateRequest,
    agent_id: Annotated[int, Query(gt=0)],
    db: Session = Depends(get_db),
):
    saved = get_memory(db, memory_id)
    if saved is None or saved.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Memory not found for this Agent")
    try:
        return update_agent_memory(db, saved, memory.content, memory.expected_content)
    except MemoryEditConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


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
