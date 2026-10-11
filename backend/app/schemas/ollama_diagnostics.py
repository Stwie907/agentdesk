"""Installation observations; they do not certify inference or embedding support."""

from typing import Literal

from pydantic import BaseModel, Field, StrictBool, model_validator


def canonical_model_name(name: str) -> str:
    name = name.strip()
    return name if ":" in name.rsplit("/", 1)[-1] else name + ":latest"


class OllamaModelObservation(BaseModel):
    configured_model: str | None
    status: Literal["installed", "missing", "unknown", "not_selected", "not_configured", "not_required"]
    installed_name: str | None = None


class OllamaModelChecks(BaseModel):
    chat: OllamaModelObservation
    planner: OllamaModelObservation
    embedding: OllamaModelObservation


class OllamaDiagnosticsResponse(BaseModel):
    schema_version: Literal[1] = 1
    read_only: StrictBool = True
    inference_performed: StrictBool = False
    model_probe_performed: StrictBool
    llm_provider: Literal["ollama", "mock"]
    selected_agent_id: int | None = Field(default=None, gt=0, le=9223372036854775807)
    memory_retrieval_mode: Literal["keyword", "semantic"]
    connection_status: Literal["available", "unreachable", "timeout", "http_error", "invalid_response", "not_required"]
    model_count: int | None = Field(default=None, ge=0, le=1000)
    models: OllamaModelChecks

    @model_validator(mode="after")
    def validate_observations(self):
        if not self.read_only or self.inference_performed:
            raise ValueError("Diagnostics must only read model metadata.")
        mock = self.llm_provider == "mock"
        if self.model_probe_performed != (not mock) or (self.connection_status == "not_required") != mock:
            raise ValueError("Probe state does not match the provider.")
        available = self.connection_status == "available"
        if (self.model_count is not None) != available:
            raise ValueError("Only a successful inventory read has a model count.")
        for role in ("chat", "planner", "embedding"):
            item = getattr(self.models, role)
            if role == "chat" and self.selected_agent_id is not None and item.configured_model is None:
                raise ValueError("Scoped diagnostics must retain the saved chat model.")
            if role == "chat" and self.selected_agent_id is None:
                expected = {"not_selected"}
                if item.configured_model is not None:
                    raise ValueError("Global diagnostics must not select a chat model.")
            elif mock or (role == "embedding" and self.memory_retrieval_mode == "keyword"):
                expected = {"not_required"}
            elif not item.configured_model or not item.configured_model.strip():
                expected = {"not_configured"}
            else:
                expected = {"installed", "missing"} if available else {"unknown"}
            if item.status not in expected:
                raise ValueError("Model observation is inconsistent with its role or probe state.")
            if (item.installed_name is not None) != (item.status == "installed"):
                raise ValueError("Only an installed model has a matched inventory name.")
            if item.status == "installed" and (
                self.model_count == 0 or not item.installed_name.strip() or not item.configured_model
                or canonical_model_name(item.installed_name) != canonical_model_name(item.configured_model)
            ):
                raise ValueError("Installed model does not match the configured model tag.")
            if role != "chat" and (not item.configured_model or not item.configured_model.strip()):
                raise ValueError("Planner and embedding configuration must not be blank.")
        return self
