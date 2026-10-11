import type { ConversationMessage } from "../types/conversations";
import { ApiError, requestJson } from "./executions";
import { compareSearchMessages, validateSavedMessage } from "./messageSearch";

export type MessageContext = {
  conversation_id: number; agent_id: number; anchor_message_id: number;
  before: number; after: number; anchor_index: number;
  has_more_before: boolean; has_more_after: boolean; items: ConversationMessage[];
};

export async function getMessageContext(
  conversationId: number, agentId: number, messageId: number, before = 3, after = 3, signal?: AbortSignal,
): Promise<MessageContext> {
  if (![conversationId, agentId, messageId].every((id) => Number.isSafeInteger(id) && id > 0) ||
      ![before, after].every((count) => Number.isInteger(count) && count >= 0 && count <= 10)) {
    throw new ApiError(422, "Use valid saved-message identities and 0 to 10 messages on each side.");
  }
  const params = new URLSearchParams({ agent_id: String(agentId), before: String(before), after: String(after) });
  const value = await requestJson<unknown>(`/conversations/${conversationId}/messages/${messageId}/context?${params}`,
    { cache: "no-store", signal });
  const page = value as Partial<MessageContext> | null;
  if (!page || page.conversation_id !== conversationId || page.agent_id !== agentId || page.anchor_message_id !== messageId ||
      page.before !== before || page.after !== after || !Number.isSafeInteger(page.anchor_index) || page.anchor_index! < 0 ||
      page.anchor_index! > before || typeof page.has_more_before !== "boolean" || typeof page.has_more_after !== "boolean" ||
      !Array.isArray(page.items) || page.items.length < 1 || page.items.length > before + 1 + after ||
      page.anchor_index! >= page.items.length || page.items.length - page.anchor_index! - 1 > after ||
      (page.has_more_before && page.anchor_index !== before) ||
      (page.has_more_after && page.items.length - page.anchor_index! - 1 !== after)) {
    throw new ApiError(502, "The server returned invalid message context boundaries or scope.");
  }
  const items = page.items.map((row) => validateSavedMessage(row, conversationId));
  if (items[page.anchor_index!].id !== messageId || new Set(items.map((row) => row.id)).size !== items.length ||
      items.some((row, index) => index > 0 && compareSearchMessages(items[index - 1], row) >= 0)) {
    throw new ApiError(502, "The server returned a missing, duplicate, or unordered context message.");
  }
  return { ...page, items } as MessageContext;
}
