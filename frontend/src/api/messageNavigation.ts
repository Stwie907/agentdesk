import type { AgentMessageSearchItem } from "./agentMessageSearch";
import { getConversation } from "./conversations";
import { ApiError } from "./executions";
import { getSavedMessage } from "./messageSearch";
import type { Conversation } from "../types/conversations";

export type MessageNavigationTarget = { conversation: Conversation; message: AgentMessageSearchItem };

export async function getMessageNavigationTarget(
  agentId: number, item: AgentMessageSearchItem, signal?: AbortSignal,
): Promise<MessageNavigationTarget> {
  if (![agentId, item?.id, item?.conversation_id].every((id) => Number.isSafeInteger(id) && id > 0) ||
      item.agent_id !== agentId) {
    throw new ApiError(422, "Use a saved message belonging to the selected Agent.");
  }
  function checkCancellation() {
    if (signal?.aborted) throw new DOMException("Opening the saved message was cancelled.", "AbortError");
  }
  checkCancellation();
  const conversation = await getConversation(item.conversation_id, agentId, signal);
  checkCancellation();
  const saved = await getSavedMessage(item.conversation_id, agentId, item.id, signal);
  checkCancellation();
  if (saved.role !== item.role || saved.created_at !== item.created_at ||
      typeof item.snippet !== "string" || !saved.content.includes(item.snippet)) {
    throw new ApiError(502, "The saved message changed. Search Agent messages again before opening its conversation.");
  }
  return { conversation, message: { ...item, conversation_title: conversation.title } };
}
