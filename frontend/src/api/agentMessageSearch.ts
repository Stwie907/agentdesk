import { ApiError, requestJson } from "./executions";
import { compareSearchMessages, validateMessageSearchItem, type MessageRoleFilter, type MessageSearchItem } from "./messageSearch";

export type AgentMessageSearchItem = MessageSearchItem & { agent_id: number; conversation_title: string };
export type AgentMessageSearchPage = {
  agent_id: number; query: string; role: MessageRoleFilter; limit: number; offset: number;
  total: number; has_more: boolean; items: AgentMessageSearchItem[];
};

export async function searchAgentMessages(
  agentId: number, query: string, role: MessageRoleFilter = null, limit = 10, offset = 0, signal?: AbortSignal,
): Promise<AgentMessageSearchPage> {
  const normalized = query.trim();
  if (!Number.isSafeInteger(agentId) || agentId <= 0 || !normalized || [...normalized].length > 200 ||
      /[\u0000\uD800-\uDFFF]/u.test(normalized) || !Number.isInteger(limit) || limit < 1 || limit > 50 ||
      !Number.isSafeInteger(offset) || offset < 0 || (role !== null && !["user", "assistant", "system", "tool"].includes(role))) {
    throw new ApiError(422, "Use a valid Agent, role, page, and search query of 1 to 200 characters.");
  }
  const params = new URLSearchParams({ query: normalized, limit: String(limit), offset: String(offset) });
  if (role !== null) params.set("role", role);
  const value = await requestJson<unknown>(`/agents/${agentId}/messages/search?${params}`, { cache: "no-store", signal });
  const page = value as Partial<AgentMessageSearchPage> | null;
  if (!page || page.agent_id !== agentId || page.query !== normalized || page.role !== role ||
      page.limit !== limit || page.offset !== offset || !Number.isSafeInteger(page.total) || page.total! < 0 ||
      !Array.isArray(page.items) || page.items.length !== Math.min(limit, Math.max(0, page.total! - offset)) ||
      page.has_more !== (offset + page.items.length < page.total!)) {
    throw new ApiError(502, "The server returned an invalid Agent message search page. Search again.");
  }
  const items = page.items.map((value) => {
    const row = value as AgentMessageSearchItem | null;
    if (!row || row.agent_id !== agentId || !Number.isSafeInteger(row.conversation_id) || row.conversation_id <= 0 ||
        typeof row.conversation_title !== "string") {
      throw new ApiError(502, "The server returned invalid or foreign Agent message search results.");
    }
    validateMessageSearchItem(row, row.conversation_id, normalized, role);
    return row;
  });
  if (new Set(items.map((row) => row.id)).size !== items.length ||
      items.some((row, index) => index > 0 && compareSearchMessages(items[index - 1], row) <= 0)) {
    throw new ApiError(502, "The server returned duplicate or unordered Agent message search results.");
  }
  return { ...page, items } as AgentMessageSearchPage;
}
