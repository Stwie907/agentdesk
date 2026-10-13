import type { Conversation, ConversationMessage, ConversationMessagePage, ConversationPage } from "../src/types/conversations";
import { jsonResponse } from "./taskFixtures";

export function conversationPageResponse(items: Conversation[], values: Partial<ConversationPage> = {}) {
  const page = { agent_id: 7, query: "", limit: 10, offset: 0, total: items.length, ...values, items };
  return jsonResponse({ ...page, has_more: page.offset + items.length < page.total });
}

export function conversationMessagePageResponse(items: ConversationMessage[], values: Partial<ConversationMessagePage> = {}) {
  return jsonResponse({ conversation_id: items[0]?.conversation_id ?? 91, agent_id: 7, limit: 20,
    before_id: null, has_more: false, next_before_id: null, ...values, items });
}
