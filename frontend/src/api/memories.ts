import type { Memory } from "../types/memories";
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
