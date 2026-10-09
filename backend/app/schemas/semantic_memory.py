from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.memory import MemoryResponse
from app.schemas.user_memory import UserMemoryResponse


class SemanticMemoryResult(BaseModel):
    memory: MemoryResponse
    similarity: float = Field(gt=0, le=1)


class SemanticUserMemoryResult(BaseModel):
    memory: UserMemoryResponse
    similarity: float = Field(gt=0, le=1)


class SemanticSearchResponse(BaseModel):
    agent_id: int
    query: str
    limit: int
    mode: Literal["semantic"] = "semantic"
    provider: Literal["ollama", "mock"]
    model: str
    runtime_mode: Literal["keyword", "semantic"]
    min_similarity: float = Field(ge=0, le=1)
    results: list[SemanticMemoryResult]


class SemanticUserSearchResponse(SemanticSearchResponse):
    user_id: int
    results: list[SemanticUserMemoryResult]
