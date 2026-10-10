import type { ConversationMessage } from "../types/conversations";
import { ApiError, requestJson } from "./executions";

export type MessageRoleFilter = "user" | "assistant" | "system" | "tool" | null;
export type MessageSearchItem = Omit<ConversationMessage, "content"> & {
  snippet: string;
  match_start: number;
  match_end: number;
  truncated_before: boolean;
  truncated_after: boolean;
};
export type MessageSearchPage = {
  conversation_id: number; agent_id: number; query: string; role: MessageRoleFilter;
  limit: number; offset: number; total: number; has_more: boolean; items: MessageSearchItem[];
};

export function asciiLower(text: string): string {
  return text.replace(/[A-Z]/g, (letter) => letter.toLowerCase());
}

function timestampKey(value: unknown): string {
  const parts = typeof value === "string" ? /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?$/.exec(value) : null;
  if (parts) {
    const [year, month, day, hour, minute, second] = parts.slice(1, 7).map(Number);
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const days = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (year > 0 && month > 0 && month <= 12 && day > 0 && day <= days[month - 1] && hour < 24 && minute < 60 && second < 60) {
      return (value as string).slice(0, 19) + "." + (parts[7] ?? "").padEnd(6, "0");
    }
  }
  throw new ApiError(502, "The server returned an invalid saved-message timestamp.");
}

function validIdentity(value: unknown, conversationId: number): boolean {
  const row = value as Partial<ConversationMessage> | null;
  return !!row && Number.isSafeInteger(row.id) && row.id! > 0 && row.conversation_id === conversationId && typeof row.role === "string";
}

export function compareSearchMessages(left: MessageSearchItem, right: MessageSearchItem): number {
  const a = timestampKey(left.created_at), b = timestampKey(right.created_at);
  return a === b ? left.id - right.id : a < b ? -1 : 1;
}

export async function searchConversationMessages(
  conversationId: number, agentId: number, query: string, role: MessageRoleFilter = null, limit = 10, offset = 0,
  signal?: AbortSignal,
): Promise<MessageSearchPage> {
  const normalized = query.trim();
  if (!normalized || [...normalized].length > 200 || /[\u0000\uD800-\uDFFF]/u.test(normalized) ||
      !Number.isSafeInteger(conversationId) || conversationId <= 0 || !Number.isSafeInteger(agentId) || agentId <= 0 ||
      !Number.isInteger(limit) || limit < 1 || limit > 50 || !Number.isSafeInteger(offset) || offset < 0 ||
      (role !== null && !["user", "assistant", "system", "tool"].includes(role))) {
    throw new ApiError(422, "Use a valid conversation, Agent, role, page, and search query of 1 to 200 characters.");
  }
  const params = new URLSearchParams({ agent_id: String(agentId), query: normalized, limit: String(limit), offset: String(offset) });
  if (role !== null) params.set("role", role);
  const value = await requestJson<unknown>(`/conversations/${conversationId}/messages/search?${params}`, { cache: "no-store", signal });
  const page = value as Partial<MessageSearchPage> | null;
  if (!page || page.conversation_id !== conversationId || page.agent_id !== agentId || page.query !== normalized ||
      page.role !== role || page.limit !== limit || page.offset !== offset || !Number.isSafeInteger(page.total) || page.total! < 0 ||
      !Array.isArray(page.items) || page.items.length !== Math.min(limit, Math.max(0, page.total! - offset)) ||
      page.has_more !== (offset + page.items.length < page.total!)) {
    throw new ApiError(502, "The server returned an invalid message search page. Search again.");
  }
  const items = page.items.map((value) => {
    const row = value as MessageSearchItem;
    if (!validIdentity(row, conversationId) || (role !== null && row.role !== role) || typeof row.snippet !== "string" ||
        typeof row.truncated_before !== "boolean" || typeof row.truncated_after !== "boolean") {
      throw new ApiError(502, "The server returned invalid or foreign message search results.");
    }
    timestampKey(row.created_at);
    const characters = [...row.snippet];
    if (characters.length === 0 || characters.length > 240 || !Number.isSafeInteger(row.match_start) ||
        !Number.isSafeInteger(row.match_end) || row.match_start < 0 || row.match_end <= row.match_start ||
        row.match_end > characters.length || asciiLower(characters.slice(row.match_start, row.match_end).join("")) !== asciiLower(normalized)) {
      throw new ApiError(502, "The server returned invalid message previews or match positions.");
    }
    return row;
  });
  if (new Set(items.map((row) => row.id)).size !== items.length ||
      items.some((row, index) => index > 0 && compareSearchMessages(items[index - 1], row) <= 0)) {
    throw new ApiError(502, "The server returned duplicate or unordered message search results.");
  }
  return { ...page, items } as MessageSearchPage;
}

export async function getSavedMessage(conversationId: number, agentId: number, messageId: number, signal?: AbortSignal): Promise<ConversationMessage> {
  if (![conversationId, agentId, messageId].every((id) => Number.isSafeInteger(id) && id > 0)) {
    throw new ApiError(422, "Use valid saved-message identities.");
  }
  const value = await requestJson<unknown>(`/conversations/${conversationId}/messages/${messageId}?agent_id=${agentId}`,
    { cache: "no-store", signal });
  const row = value as ConversationMessage;
  if (!validIdentity(row, conversationId) || row.id !== messageId || typeof row.content !== "string") {
    throw new ApiError(502, "The server returned a different or invalid saved message.");
  }
  timestampKey(row.created_at);
  return row;
}
