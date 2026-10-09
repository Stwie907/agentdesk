from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user_memory import UserMemory
from app.schemas.user_memory import (
    UserMemoryCreateRequest, UserMemoryListResponse, UserMemoryResponse,
    UserMemorySearchResponse, UserMemorySearchResult, UserMemoryUpdateRequest,
)
from app.services.user_memory_service import (
    UserMemoryConflict, delete_user_memory, list_user_memories, owner_for_agent,
    ranked_user_memories_for_agent, save_user_memory, update_user_memory,
)
from app.schemas.semantic_memory import SemanticUserMemoryResult, SemanticUserSearchResponse
from app.services.memory_embeddings import SemanticMemoryUnavailable, get_embedding_settings
from app.services.semantic_memory import rank_semantic_rows


router = APIRouter(prefix="/user-memories", tags=["user memories"])


def require_owner(db: Session, agent_id: int, user_id: int | None = None):
    owner = owner_for_agent(db, agent_id)
    if owner is None:
        raise HTTPException(status_code=404, detail="Agent or its Project owner not found")
    if user_id is not None and owner.id != user_id:
        raise HTTPException(status_code=404, detail="User does not own this Agent")
    return owner


def scoped_memory(db: Session, agent_id: int, user_id: int, memory_id: int):
    owner = require_owner(db, agent_id, user_id)
    memory = db.query(UserMemory).filter_by(id=memory_id, user_id=owner.id).first()
    if memory is None:
        raise HTTPException(status_code=404, detail="Shared memory not found for this User")
    return memory


@router.get("/for-agent/{agent_id}", response_model=UserMemoryListResponse)
def read(agent_id: Annotated[int, Path(gt=0)], db: Session = Depends(get_db)):
    owner = require_owner(db, agent_id)
    return UserMemoryListResponse(agent_id=agent_id, user_id=owner.id, username=owner.username,
                                 memories=list_user_memories(db, owner.id))


@router.post("/for-agent/{agent_id}", response_model=UserMemoryResponse)
def create(agent_id: Annotated[int, Path(gt=0)], memory: UserMemoryCreateRequest, db: Session = Depends(get_db)):
    owner = require_owner(db, agent_id, memory.user_id)
    try:
        return save_user_memory(db, owner.id, memory.content)
    except UserMemoryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/for-agent/{agent_id}/search", response_model=UserMemorySearchResponse)
def search(agent_id: Annotated[int, Path(gt=0)], query: Annotated[str, Query(min_length=1, max_length=500)],
           db: Session = Depends(get_db), limit: Annotated[int, Query(ge=1, le=20)] = 5):
    owner = require_owner(db, agent_id)
    normalized = query.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Enter a non-blank shared memory query")
    matches = ranked_user_memories_for_agent(db, agent_id, normalized, limit)
    return UserMemorySearchResponse(agent_id=agent_id, user_id=owner.id, query=normalized, limit=limit,
        results=[UserMemorySearchResult(memory=UserMemoryResponse.model_validate(match.memory),
            score=match.score, matched_terms=list(match.matched_terms)) for match in matches])


@router.get("/for-agent/{agent_id}/semantic-search", response_model=SemanticUserSearchResponse)
def search_shared_semantically(
    agent_id: Annotated[int, Path(gt=0)],
    query: Annotated[str, Query(min_length=1, max_length=500)],
    db: Session = Depends(get_db),
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    min_similarity: Annotated[float | None, Query(ge=0, le=1, allow_inf_nan=False)] = None,
):
    normalized = query.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail="Enter a non-blank semantic memory query")
    owner = require_owner(db, agent_id)
    rows = list_user_memories(db, owner.id)
    try:
        settings = get_embedding_settings()
        minimum = settings.memory.min_similarity if min_similarity is None else min_similarity
        matches = rank_semantic_rows(rows, normalized, settings, limit, minimum)
    except SemanticMemoryUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return SemanticUserSearchResponse(agent_id=agent_id, user_id=owner.id, query=normalized, limit=limit,
        provider=settings.provider, model=settings.model, runtime_mode=settings.memory.mode,
        min_similarity=minimum, results=[SemanticUserMemoryResult(memory=UserMemoryResponse.model_validate(match.memory),
                                                                  similarity=match.similarity) for match in matches])


@router.patch("/item/{memory_id}", response_model=UserMemoryResponse)
def update(memory_id: Annotated[int, Path(gt=0)], memory: UserMemoryUpdateRequest,
           agent_id: Annotated[int, Query(gt=0)], user_id: Annotated[int, Query(gt=0)], db: Session = Depends(get_db)):
    saved = scoped_memory(db, agent_id, user_id, memory_id)
    try:
        return update_user_memory(db, saved, memory.content, memory.expected_content)
    except UserMemoryConflict as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/item/{memory_id}")
def remove(memory_id: Annotated[int, Path(gt=0)], agent_id: Annotated[int, Query(gt=0)],
           user_id: Annotated[int, Query(gt=0)], db: Session = Depends(get_db)):
    delete_user_memory(db, scoped_memory(db, agent_id, user_id, memory_id))
    return {"message": "Shared memory deleted successfully"}
