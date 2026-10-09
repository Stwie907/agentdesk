from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints


class MemoryCreate(BaseModel):
    agent_id: int
    content: str


class MemoryCreateRequest(MemoryCreate):
    """Validate manual API writes without changing internal extraction inputs."""

    agent_id: Annotated[int, Field(strict=True, gt=0)]
    content: Annotated[
        str,
        StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=2000),
    ]


class MemoryResponse(BaseModel):
    id: int
    agent_id: int
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class MemorySearchResult(BaseModel):
    memory: MemoryResponse
    score: int
    matched_terms: list[str]


class MemorySearchResponse(BaseModel):
    agent_id: int
    query: str
    limit: int
    results: list[MemorySearchResult]

