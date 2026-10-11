"""Read effective process settings and an optional Agent model without probes."""

from sqlalchemy.orm import Session

from app.config import get_llm_settings
from app.memory_config import get_memory_settings
from app.models.agent import Agent
from app.schemas.runtime_configuration import (
    RuntimeAgentConfiguration, RuntimeConfigurationResponse, RuntimeMemoryConfiguration,
)


def runtime_configuration(db: Session, agent: Agent | None = None) -> RuntimeConfigurationResponse:
    llm = get_llm_settings()
    memory = get_memory_settings()
    semantic = memory.mode == "semantic"
    active_embedding_model = None
    if semantic:
        active_embedding_model = "mock-fixtures-v1" if llm.provider == "mock" else memory.embedding_model
    return RuntimeConfigurationResponse(
        llm_provider=llm.provider,
        configured_planner_model=llm.planner_model,
        selected_agent=None if agent is None else RuntimeAgentConfiguration(id=agent.id, chat_model=agent.model),
        memory=RuntimeMemoryConfiguration(
            retrieval_mode=memory.mode,
            configured_embedding_model=memory.embedding_model,
            active_embedding_model=active_embedding_model,
            min_similarity=memory.min_similarity,
            vector_cache_enabled=memory.cache_enabled,
            vector_cache_active=semantic and memory.cache_enabled,
        ),
        database_backend=db.get_bind().dialect.name,
    )
