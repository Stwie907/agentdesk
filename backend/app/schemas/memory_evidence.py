"""Versioned facts captured when Runtime builds its memory prompt."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


PositiveId = Annotated[int, Field(strict=True, gt=0)]
Similarity = Annotated[float, Field(strict=True, gt=0, le=1, allow_inf_nan=False)]


class MemoryEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_id: PositiveId
    scope: Literal["agent", "user"]
    scope_id: PositiveId
    content: str
    created_at: datetime = Field(strict=True)
    score: Annotated[int, Field(strict=True, ge=0)] | None
    matched_terms: list[str]
    similarity: Similarity | None


def render_memory_context(agent_memories, shared_memories) -> str:
    agent = "\n".join(row.content for row in agent_memories)
    shared = "\n".join(row.content for row in shared_memories)
    if not shared:
        return agent
    return "Shared user memory:\n" + shared + ("\nAgent memory:\n" + agent if agent else "")


class MemoryEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    agent_id: PositiveId
    user_id: PositiveId | None
    query: str
    limit: Annotated[int, Field(strict=True, ge=0)]
    recorded_at: datetime = Field(strict=True)
    requested_mode: Literal["keyword", "semantic"]
    mode: Literal["keyword", "semantic"]
    provider: Literal["mock", "ollama"] | None
    model: str | None
    min_similarity: Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)] | None
    fallback_reason: str | None
    agent_memories: list[MemoryEvidenceItem]
    shared_memories: list[MemoryEvidenceItem]
    context: str

    @field_validator("version", mode="before")
    @classmethod
    def require_integer_version(cls, value):
        if type(value) is not int:
            raise ValueError("Evidence version must be an integer")
        return value

    @model_validator(mode="after")
    def validate_capture(self):
        if self.query != self.query.strip():
            raise ValueError("Captured query must be trimmed")
        if self.mode == "semantic":
            if (self.requested_mode != "semantic" or not self.query or self.limit == 0
                    or self.provider is None or not self.model or not self.model.strip()
                    or self.min_similarity is None or self.fallback_reason is not None):
                raise ValueError("Semantic evidence has inconsistent retrieval metadata")
        elif self.provider is not None or self.model is not None or self.min_similarity is not None:
            raise ValueError("Keyword evidence cannot claim an embedding provider or score threshold")
        if self.fallback_reason is not None and not self.fallback_reason.strip():
            raise ValueError("Fallback reason must describe the failure")
        if (self.requested_mode == "semantic" and self.mode == "keyword" and self.query
                and self.limit > 0 and self.fallback_reason is None):
            raise ValueError("A semantic fallback must include its reason")
        for scope, owner, rows in (("agent", self.agent_id, self.agent_memories),
                                   ("user", self.user_id, self.shared_memories)):
            if len(rows) > self.limit or len({row.memory_id for row in rows}) != len(rows):
                raise ValueError("Captured memory limit or identity is invalid")
            for row in rows:
                if row.scope != scope or owner is None or row.scope_id != owner:
                    raise ValueError("Captured memory crosses its execution scope")
                if self.mode == "semantic":
                    if (row.similarity is None or row.similarity < self.min_similarity
                            or row.score is not None or row.matched_terms):
                        raise ValueError("Semantic result has inconsistent scores")
                elif (row.similarity is not None or row.score is None
                      or row.score != len(row.matched_terms)
                      or row.matched_terms != sorted(set(row.matched_terms))
                      or any(not term for term in row.matched_terms)
                      or (bool(self.query) and row.score == 0)
                      or (not self.query and row.score != 0)):
                    raise ValueError("Keyword result has inconsistent scores")
            if self.query:
                keys = [(row.similarity if self.mode == "semantic" else row.score, row.memory_id) for row in rows]
                if keys != sorted(keys, reverse=True):
                    raise ValueError("Captured results are not in retrieval order")
        if self.context != render_memory_context(self.agent_memories, self.shared_memories):
            raise ValueError("Captured context differs from its selected memories")
        return self


class ExecutionMemoryContext(BaseModel):
    execution_id: PositiveId
    available: bool
    evidence: MemoryEvidence | None
