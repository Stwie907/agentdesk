"""Public runtime settings, without endpoints, credentials or database paths."""

from typing import Literal

from pydantic import BaseModel, Field, StrictBool, model_validator


class RuntimeAgentConfiguration(BaseModel):
    id: int = Field(gt=0, le=9223372036854775807)
    chat_model: str


class RuntimeMemoryConfiguration(BaseModel):
    retrieval_mode: Literal["keyword", "semantic"]
    configured_embedding_model: str = Field(min_length=1)
    active_embedding_model: str | None
    min_similarity: float = Field(ge=0, le=1, allow_inf_nan=False)
    vector_cache_enabled: StrictBool
    vector_cache_active: StrictBool

    @model_validator(mode="after")
    def validate_active_settings(self):
        semantic = self.retrieval_mode == "semantic"
        if self.vector_cache_active != (semantic and self.vector_cache_enabled):
            raise ValueError("Vector cache activity does not match the retrieval mode.")
        if (semantic and not self.active_embedding_model) or (not semantic and self.active_embedding_model is not None):
            raise ValueError("Embedding activity does not match the retrieval mode.")
        return self


class RuntimeConfigurationResponse(BaseModel):
    schema_version: Literal[1] = 1
    read_only: StrictBool = True
    model_probe_performed: StrictBool = False
    llm_provider: Literal["ollama", "mock"]
    configured_planner_model: str = Field(min_length=1)
    selected_agent: RuntimeAgentConfiguration | None
    memory: RuntimeMemoryConfiguration
    database_backend: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_contract(self):
        if not self.read_only or self.model_probe_performed:
            raise ValueError("Runtime configuration must be a read-only settings view.")
        if self.memory.retrieval_mode == "semantic":
            expected = "mock-fixtures-v1" if self.llm_provider == "mock" else self.memory.configured_embedding_model
            if self.memory.active_embedding_model != expected:
                raise ValueError("Active embedding model does not match the provider.")
        return self
