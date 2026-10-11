import { ApiError, requestJson } from "./executions";

export type RuntimeConfiguration = {
  schema_version: 1;
  read_only: true;
  model_probe_performed: false;
  llm_provider: "ollama" | "mock";
  configured_planner_model: string;
  selected_agent: { id: number; chat_model: string } | null;
  memory: {
    retrieval_mode: "keyword" | "semantic";
    configured_embedding_model: string;
    active_embedding_model: string | null;
    min_similarity: number;
    vector_cache_enabled: boolean;
    vector_cache_active: boolean;
  };
  database_backend: string;
};

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonblank(value: unknown): value is string {
  return typeof value === "string" && value.trim() !== "";
}

function checkAbort(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("Runtime configuration read was cancelled.", "AbortError");
}

export function validateRuntimeConfiguration(value: unknown, agentId: number | null): RuntimeConfiguration {
  const invalid = () => new ApiError(502, "Runtime configuration response is invalid or belongs to another Agent.");
  if (!object(value) || value.schema_version !== 1 || value.read_only !== true || value.model_probe_performed !== false ||
      !["ollama", "mock"].includes(value.llm_provider as string) || !nonblank(value.configured_planner_model) ||
      !nonblank(value.database_backend) || !object(value.memory)) throw invalid();
  if (agentId === null) {
    if (value.selected_agent !== null) throw invalid();
  } else if (!object(value.selected_agent) || value.selected_agent.id !== agentId || typeof value.selected_agent.chat_model !== "string") {
    throw invalid();
  }
  const memory = value.memory;
  if (!["keyword", "semantic"].includes(memory.retrieval_mode as string) || !nonblank(memory.configured_embedding_model) ||
      typeof memory.min_similarity !== "number" || !Number.isFinite(memory.min_similarity) || memory.min_similarity < 0 || memory.min_similarity > 1 ||
      typeof memory.vector_cache_enabled !== "boolean" || typeof memory.vector_cache_active !== "boolean") throw invalid();
  const semantic = memory.retrieval_mode === "semantic";
  const expectedModel = semantic ? (value.llm_provider === "mock" ? "mock-fixtures-v1" : memory.configured_embedding_model) : null;
  if (memory.active_embedding_model !== expectedModel || memory.vector_cache_active !== (semantic && memory.vector_cache_enabled)) throw invalid();
  return value as RuntimeConfiguration;
}

export async function getRuntimeConfiguration(agentId: number | null, signal?: AbortSignal): Promise<RuntimeConfiguration> {
  checkAbort(signal);
  if (agentId !== null && (!Number.isSafeInteger(agentId) || agentId <= 0)) {
    throw new ApiError(422, "Select a valid Agent before reading its runtime configuration.");
  }
  const path = agentId === null ? "/runtime/config" : `/runtime/config?agent_id=${agentId}`;
  let value: unknown;
  try {
    value = await requestJson<unknown>(path, { cache: "no-store", signal });
  } catch (error) {
    checkAbort(signal);
    if (error instanceof SyntaxError) throw new ApiError(502, "Runtime configuration did not return valid JSON.");
    throw error;
  }
  checkAbort(signal);
  return validateRuntimeConfiguration(value, agentId);
}
