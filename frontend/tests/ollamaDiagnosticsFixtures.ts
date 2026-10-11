import type { OllamaDiagnostics } from "../src/api/ollamaDiagnostics";

export function installedModels(agentId: number | null = 7): OllamaDiagnostics {
  return {
    schema_version: 1, read_only: true, inference_performed: false, model_probe_performed: true,
    llm_provider: "ollama", selected_agent_id: agentId, memory_retrieval_mode: "semantic",
    connection_status: "available", model_count: 2,
    models: {
      chat: { configured_model: agentId === null ? null : "qwen2.5:7b", status: agentId === null ? "not_selected" : "installed", installed_name: agentId === null ? null : "qwen2.5:7b" },
      planner: { configured_model: "qwen2.5:7b", status: "installed", installed_name: "qwen2.5:7b" },
      embedding: { configured_model: "embeddinggemma", status: "installed", installed_name: "embeddinggemma:latest" },
    },
  };
}

export function failedModels(status: "unreachable" | "timeout" | "http_error" | "invalid_response"): OllamaDiagnostics {
  const value = installedModels();
  value.connection_status = status; value.model_count = null;
  Object.values(value.models).forEach((model) => { model.status = "unknown"; model.installed_name = null; });
  return value;
}
