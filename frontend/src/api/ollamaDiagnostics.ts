import { ApiError, requestJson } from "./executions";

export type ModelObservation = {
  configured_model: string | null;
  status: "installed" | "missing" | "unknown" | "not_selected" | "not_configured" | "not_required";
  installed_name: string | null;
};

export type OllamaDiagnostics = {
  schema_version: 1;
  read_only: true;
  inference_performed: false;
  model_probe_performed: boolean;
  llm_provider: "ollama" | "mock";
  selected_agent_id: number | null;
  memory_retrieval_mode: "keyword" | "semantic";
  connection_status: "available" | "unreachable" | "timeout" | "http_error" | "invalid_response" | "not_required";
  model_count: number | null;
  models: { chat: ModelObservation; planner: ModelObservation; embedding: ModelObservation };
};

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function canonical(name: string): string {
  name = name.trim();
  return name.split("/").at(-1)!.includes(":") ? name : name + ":latest";
}

function cancelled(signal?: AbortSignal): void {
  if (signal?.aborted) throw new DOMException("Model check was cancelled.", "AbortError");
}

export function validateOllamaDiagnostics(value: unknown, agentId: number | null): OllamaDiagnostics {
  const invalid = () => new ApiError(502, "Local model check returned an invalid response or another Agent's result.");
  if (!object(value) || value.schema_version !== 1 || value.read_only !== true || value.inference_performed !== false ||
      typeof value.model_probe_performed !== "boolean" || !["ollama", "mock"].includes(value.llm_provider as string) ||
      value.selected_agent_id !== agentId || !["keyword", "semantic"].includes(value.memory_retrieval_mode as string) ||
      !["available", "unreachable", "timeout", "http_error", "invalid_response", "not_required"].includes(value.connection_status as string) ||
      !object(value.models)) throw invalid();
  const mock = value.llm_provider === "mock", available = value.connection_status === "available";
  if (value.model_probe_performed !== !mock || (value.connection_status === "not_required") !== mock ||
      (available ? !Number.isInteger(value.model_count) || (value.model_count as number) < 0 || (value.model_count as number) > 1000 : value.model_count !== null)) throw invalid();
  for (const role of ["chat", "planner", "embedding"] as const) {
    const item = value.models[role];
    if (!object(item) || !(item.configured_model === null || typeof item.configured_model === "string") ||
        !(item.installed_name === null || typeof item.installed_name === "string")) throw invalid();
    if (role === "chat" && agentId !== null && typeof item.configured_model !== "string") throw invalid();
    if (role !== "chat" && (typeof item.configured_model !== "string" || item.configured_model.trim() === "")) throw invalid();
    let expected: string[];
    if (role === "chat" && agentId === null) {
      if (item.configured_model !== null) throw invalid();
      expected = ["not_selected"];
    } else if (mock || (role === "embedding" && value.memory_retrieval_mode === "keyword")) {
      expected = ["not_required"];
    } else if (!item.configured_model || item.configured_model.trim() === "") {
      expected = ["not_configured"];
    } else expected = available ? ["installed", "missing"] : ["unknown"];
    if (!expected.includes(item.status as string) || (item.installed_name !== null) !== (item.status === "installed")) throw invalid();
    if (item.status === "installed" && (value.model_count === 0 || !item.installed_name || !item.configured_model ||
        item.installed_name.trim() === "" || canonical(item.installed_name) !== canonical(item.configured_model))) throw invalid();
  }
  return value as OllamaDiagnostics;
}

export async function getOllamaDiagnostics(agentId: number | null, signal?: AbortSignal): Promise<OllamaDiagnostics> {
  cancelled(signal);
  if (agentId !== null && (!Number.isSafeInteger(agentId) || agentId <= 0)) throw new ApiError(422, "Select a valid Agent before checking local models.");
  const path = "/runtime/ollama" + (agentId === null ? "" : "?agent_id=" + agentId);
  let value: unknown;
  try {
    value = await requestJson<unknown>(path, { cache: "no-store", signal });
  } catch (error) {
    cancelled(signal);
    if (error instanceof SyntaxError) throw new ApiError(502, "Local model check did not return valid JSON.");
    throw error;
  }
  cancelled(signal);
  return validateOllamaDiagnostics(value, agentId);
}
