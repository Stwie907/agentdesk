import type { UserMemory, UserMemoryList, UserMemorySearch } from "../types/userMemories";
import { ApiError, requestJson } from "./executions";

function invalid(): ApiError { return new ApiError(502, "The server returned invalid shared memory data."); }

function validateMemory(value: unknown, userId: number): UserMemory {
  if (!value || typeof value !== "object") throw invalid();
  const row = value as Partial<UserMemory>;
  if (!Number.isInteger(row.id) || (row.id ?? 0) <= 0 || row.user_id !== userId ||
      typeof row.content !== "string" || typeof row.created_at !== "string") throw invalid();
  return row as UserMemory;
}

export async function getUserMemories(agentId: number): Promise<UserMemoryList> {
  const value = await requestJson<Partial<UserMemoryList>>(`/user-memories/for-agent/${agentId}`, { cache: "no-store" });
  if (!value || value.agent_id !== agentId || !Number.isInteger(value.user_id) || (value.user_id ?? 0) <= 0 ||
      typeof value.username !== "string" || !Array.isArray(value.memories)) throw invalid();
  const memories = value.memories.map((row) => validateMemory(row, value.user_id!));
  if (new Set(memories.map(row => row.id)).size !== memories.length) throw invalid();
  return { agent_id: agentId, user_id: value.user_id!, username: value.username, memories };
}

async function write(path: string, method: string, payload: unknown, userId: number): Promise<UserMemory> {
  try {
    const row = await requestJson<unknown>(path, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    return validateMemory(row, userId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) throw new ApiError(422, "Use shared memory content of 1 to 2000 characters.");
    throw error;
  }
}

export async function saveUserMemory(agentId: number, userId: number, content: string): Promise<UserMemory> {
  const saved = await write(`/user-memories/for-agent/${agentId}`, "POST", { user_id: userId, content: content.trim() }, userId);
  if (saved.content !== content.trim()) throw invalid();
  return saved;
}

export async function updateUserMemory(agentId: number, memory: UserMemory, content: string): Promise<UserMemory> {
  const saved = await write(`/user-memories/item/${memory.id}?agent_id=${agentId}&user_id=${memory.user_id}`, "PATCH",
    { content: content.trim(), expected_content: memory.content }, memory.user_id);
  if (saved.id !== memory.id || saved.created_at !== memory.created_at || saved.content !== content.trim()) throw invalid();
  return saved;
}

export async function deleteUserMemory(agentId: number, userId: number, memoryId: number): Promise<void> {
  await requestJson(`/user-memories/item/${memoryId}?agent_id=${agentId}&user_id=${userId}`, { method: "DELETE" });
}

export async function searchUserMemories(agentId: number, userId: number, query: string): Promise<UserMemorySearch> {
  const normalized = query.trim();
  const params = new URLSearchParams({ query: normalized, limit: "5" });
  try {
    const value = await requestJson<Partial<UserMemorySearch>>(`/user-memories/for-agent/${agentId}/search?${params}`, { cache: "no-store" });
    if (!value || value.agent_id !== agentId || value.user_id !== userId || value.query !== normalized || value.limit !== 5 ||
        !Array.isArray(value.results) || value.results.length > 5) throw invalid();
    const ids = new Set<number>();
    const results: UserMemorySearch["results"] = [];
    for (const row of value.results) {
      if (!row || !Number.isInteger(row.score) || row.score <= 0 || !Array.isArray(row.matched_terms) ||
          row.matched_terms.some(term => typeof term !== "string" || !term) ||
          row.score !== new Set(row.matched_terms).size || row.score !== row.matched_terms.length) throw invalid();
      const memory = validateMemory(row.memory, userId);
      const previous = results.at(-1);
      if (ids.has(memory.id) || (previous && (previous.score < row.score ||
          previous.score === row.score && previous.memory.id < memory.id))) throw invalid();
      ids.add(memory.id);
      results.push({ memory, score: row.score, matched_terms: row.matched_terms });
    }
    return { agent_id: agentId, user_id: userId, query: normalized, limit: 5, results };
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) throw new ApiError(422, "Enter a shared memory query of 1 to 500 characters.");
    throw error;
  }
}
