from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.memory import MemoryUpdateRequest


class UserMemoryCreateRequest(BaseModel):
    user_id: Annotated[int, Field(strict=True, gt=0)]
    content: Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000)]
    model_config = {"extra": "forbid"}


class UserMemoryUpdateRequest(MemoryUpdateRequest):
    pass


class UserMemoryResponse(BaseModel):
    id: int
    user_id: int
    content: str
    created_at: datetime
    model_config = {"from_attributes": True}


class UserMemoryListResponse(BaseModel):
    agent_id: int
    user_id: int
    username: str
    memories: list[UserMemoryResponse]


class UserMemorySearchResult(BaseModel):
    memory: UserMemoryResponse
    score: int
    matched_terms: list[str]


class UserMemorySearchResponse(BaseModel):
    agent_id: int
    user_id: int
    query: str
    limit: int
    results: list[UserMemorySearchResult]
