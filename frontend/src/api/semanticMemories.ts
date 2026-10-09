import { ApiError, requestJson } from "./executions";
import type { Memory } from "../types/memories";
import type { UserMemory } from "../types/userMemories";

export type SemanticSearch<T extends Memory | UserMemory> = {
  agent_id: number;
  user_id?: number;
  query: string;
  limit: number;
  mode: "semantic";
  provider: "ollama" | "mock";
  model: string;
  runtime_mode: "keyword" | "semantic";
  min_similarity: number;
  results: { memory: T; similarity: number }[];
};

async function search<T extends Memory | UserMemory>(agentId: number, query: string, limit: number, userId?: number): Promise<SemanticSearch<T>> {
  const normalized = query.trim();
  const params = new URLSearchParams({ query: normalized, limit: String(limit) });
  const prefix = userId === undefined ? `/memories/${agentId}` : `/user-memories/for-agent/${agentId}`;
  const invalid = () => new ApiError(502, "The server returned invalid semantic memory search data.");
  try {
    const value = await requestJson<Partial<SemanticSearch<T>>>(`${prefix}/semantic-search?${params}`, { cache: "no-store" });
    if (!value || value.agent_id !== agentId || value.query !== normalized || value.limit !== limit || value.mode !== "semantic" ||
        (value.provider !== "mock" && value.provider !== "ollama") || typeof value.model !== "string" || !value.model.trim() ||
        (value.runtime_mode !== "keyword" && value.runtime_mode !== "semantic") ||
        typeof value.min_similarity !== "number" || !Number.isFinite(value.min_similarity) || value.min_similarity < 0 || value.min_similarity > 1 ||
        (userId !== undefined && value.user_id !== userId) || !Array.isArray(value.results) || value.results.length > limit) throw invalid();
    const ids = new Set<number>();
    const results: SemanticSearch<T>["results"] = [];
    for (const row of value.results) {
      const memory = row?.memory;
      if (!memory || !Number.isInteger(memory.id) || memory.id <= 0 || typeof memory.content !== "string" ||
          typeof memory.created_at !== "string" || (userId === undefined ? !("agent_id" in memory) || memory.agent_id !== agentId
            : !("user_id" in memory) || memory.user_id !== userId) ||
          typeof row.similarity !== "number" || !Number.isFinite(row.similarity) || row.similarity <= 0 || row.similarity > 1 ||
          row.similarity < value.min_similarity || ids.has(memory.id)) throw invalid();
      const previous = results.at(-1);
      if (previous && (previous.similarity < row.similarity || previous.similarity === row.similarity && previous.memory.id < memory.id)) throw invalid();
      ids.add(memory.id);
      results.push({ memory, similarity: row.similarity });
    }
    return { ...value, results } as SemanticSearch<T>;
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) throw new ApiError(422, "Use a semantic query of 1 to 500 characters and a result limit of 1 to 20.");
    throw error;
  }
}

export function searchSemanticMemories(agentId: number, query: string, limit = 5): Promise<SemanticSearch<Memory>> {
  return search<Memory>(agentId, query, limit);
}

export function searchSemanticUserMemories(agentId: number, userId: number, query: string): Promise<SemanticSearch<UserMemory>> {
  return search<UserMemory>(agentId, query, 5, userId);
}
