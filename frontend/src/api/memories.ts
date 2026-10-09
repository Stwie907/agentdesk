import type { Memory, MemorySearchResponse, MemorySearchResult } from "../types/memories";
import { ApiError, requestJson } from "./executions";

function validateMemory(value: unknown, agentId: number): Memory {
  if (typeof value !== "object" || value === null) {
    throw new ApiError(502, "The server returned invalid memory data.");
  }
  const row = value as Partial<Memory>;
  if (
    !Number.isInteger(row.id) || (row.id ?? 0) <= 0 ||
    row.agent_id !== agentId || typeof row.content !== "string" ||
    typeof row.created_at !== "string"
  ) {
    throw new ApiError(502, "The server returned invalid memory data for this Agent.");
  }
  return row as Memory;
}

export async function getAgentMemories(agentId: number): Promise<Memory[]> {
  const rows = await requestJson<unknown>(`/memories/${agentId}`, { cache: "no-store" });
  if (!Array.isArray(rows)) {
    throw new ApiError(502, "The server returned an invalid memory list.");
  }
  return rows.map((row) => validateMemory(row, agentId));
}

export async function saveMemory(agentId: number, content: string): Promise<Memory> {
  try {
    const row = await requestJson<unknown>("/memories", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, content: content.trim() }),
    });
    return validateMemory(row, agentId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      throw new ApiError(422, "Use a valid Agent ID and memory content of 1 to 2000 characters.");
    }
    throw error;
  }
}

export async function deleteMemory(memoryId: number, agentId: number): Promise<void> {
  await requestJson(`/memories/item/${memoryId}?agent_id=${agentId}`, { method: "DELETE" });
}

export async function searchMemories(agentId: number, query: string, limit = 5): Promise<MemorySearchResponse> {
  const normalized = query.trim();
  const params = new URLSearchParams({ query: normalized, limit: String(limit) });
  try {
    const value = await requestJson<Partial<MemorySearchResponse>>(`/memories/${agentId}/search?${params}`, { cache: "no-store" });
    const invalid = () => new ApiError(502, "The server returned invalid memory search data for this Agent.");
    if (!value || value.agent_id !== agentId || value.query !== normalized || value.limit !== limit ||
        !Array.isArray(value.results) || value.results.length > limit) throw invalid();
    const results: MemorySearchResult[] = [];
    const ids = new Set<number>();
    for (const row of value.results) {
      if (!row || !Number.isInteger(row.score) || row.score <= 0 || !Array.isArray(row.matched_terms) ||
          row.matched_terms.some((term) => typeof term !== "string" || !term) ||
          new Set(row.matched_terms).size !== row.matched_terms.length || row.score !== row.matched_terms.length) throw invalid();
      const memory = validateMemory(row.memory, agentId);
      const previous = results.at(-1);
      if (ids.has(memory.id) || (previous && (previous.score < row.score ||
          (previous.score === row.score && previous.memory.id < memory.id)))) throw invalid();
      ids.add(memory.id);
      results.push({ memory, score: row.score, matched_terms: row.matched_terms });
    }
    return { agent_id: agentId, query: normalized, limit, results };
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      throw new ApiError(422, "Enter a memory search query of 1 to 500 characters and a result limit of 1 to 20.");
    }
    throw error;
  }
}
