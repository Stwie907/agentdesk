import type { ConversationMessage } from "../src/types/conversations";
import { exportMessages } from "./conversationExportFixtures";
import { messageSearchData, searchResponse } from "./messageSearchFixtures";

export function contextData(messageId = 13, before = 3, after = 3, messages: ConversationMessage[] = exportMessages) {
  const index = messages.findIndex((row) => row.id === messageId);
  return { conversation_id: 91, agent_id: 7, anchor_message_id: messageId, before, after,
    anchor_index: Math.min(index, before), has_more_before: index > before, has_more_after: messages.length - index - 1 > after,
    items: messages.slice(Math.max(0, index - before), index + after + 1).map((row) => ({ ...row })) };
}

export function contextResponse(data: unknown = contextData(), status = 200) { return searchResponse(data, status); }

export function contextPreview(messageId = 13, messages = exportMessages) {
  return messageSearchData("中文", null, 50, 0, messages).items.find((row) => row.id === messageId)!;
}
