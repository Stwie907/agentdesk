import type { Conversation, ConversationPage } from "../src/types/conversations";
import { jsonResponse } from "./taskFixtures";

export function conversationPageResponse(items: Conversation[], values: Partial<ConversationPage> = {}) {
  const page = { agent_id: 7, query: "", limit: 10, offset: 0, total: items.length, ...values, items };
  return jsonResponse({ ...page, has_more: page.offset + items.length < page.total });
}
