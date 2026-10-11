import type { RuntimeConfiguration } from "../src/api/runtimeConfiguration";

export function runtimeConfiguration(agentId: number | null = 7): RuntimeConfiguration {
  return {
    schema_version: 1, read_only: true, model_probe_performed: false,
    llm_provider: "ollama", configured_planner_model: "qwen2.5:7b",
    selected_agent: agentId === null ? null : { id: agentId, chat_model: "qwen2.5:7b" },
    memory: {
      retrieval_mode: "keyword", configured_embedding_model: "embeddinggemma", active_embedding_model: null,
      min_similarity: 0.35, vector_cache_enabled: true, vector_cache_active: false,
    },
    database_backend: "sqlite",
  };
}

export function semanticRuntimeConfiguration(agentId: number | null = 7, provider: "ollama" | "mock" = "ollama"): RuntimeConfiguration {
  const value = runtimeConfiguration(agentId);
  value.llm_provider = provider;
  value.memory.retrieval_mode = "semantic";
  value.memory.active_embedding_model = provider === "mock" ? "mock-fixtures-v1" : "embeddinggemma";
  value.memory.vector_cache_active = true;
  return value;
}
