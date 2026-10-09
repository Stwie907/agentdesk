import type { AgentChatResponse } from "../types/agents";
import type { Conversation, ConversationMessage } from "../types/conversations";
import { ApiError, requestJson } from "./executions";

function validateConversation(value: unknown, agentId: number): Conversation {
  const row = value as Partial<Conversation> | null;
  if (!row || !Number.isInteger(row.id) || (row.id ?? 0) <= 0 || row.agent_id !== agentId ||
      typeof row.title !== "string" || typeof row.created_at !== "string") {
    throw new ApiError(502, "The server returned invalid conversation data for this Agent.");
  }
  return row as Conversation;
}

export async function getConversations(agentId: number): Promise<Conversation[]> {
  const rows = await requestJson<unknown>(`/conversations?agent_id=${agentId}`, { cache: "no-store" });
  if (!Array.isArray(rows)) throw new ApiError(502, "The server returned an invalid conversation list.");
  return rows.map((row) => validateConversation(row, agentId));
}

export async function createConversation(agentId: number, title: string): Promise<Conversation> {
  try {
    const row = await requestJson<unknown>("/conversations", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ agent_id: agentId, title: title.trim() }),
    });
    return validateConversation(row, agentId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      throw new ApiError(422, "Use a valid Agent and a conversation title of 1 to 200 characters.");
    }
    throw error;
  }
}

export async function renameConversation(conversationId: number, agentId: number, title: string): Promise<Conversation> {
  try {
    const row = validateConversation(await requestJson<unknown>(`/conversations/${conversationId}?agent_id=${agentId}`, {
      method: "PATCH", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title: title.trim() }),
    }), agentId);
    if (row.id !== conversationId) throw new ApiError(502, "The server returned a different conversation. Reload conversations.");
    return row;
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      throw new ApiError(422, "Enter a conversation title of 1 to 200 characters.");
    }
    throw error;
  }
}

export async function deleteConversation(conversationId: number, agentId: number): Promise<void> {
  const reply = await requestJson<{ message?: string }>(`/conversations/${conversationId}?agent_id=${agentId}`, { method: "DELETE" });
  if (!reply || reply.message !== "deleted") {
    throw new ApiError(502, "The server returned an invalid delete result. Reload conversations before trying again.");
  }
}

export async function getConversationMessages(conversationId: number, agentId: number): Promise<ConversationMessage[]> {
  const rows = await requestJson<unknown>(`/conversations/${conversationId}/messages?agent_id=${agentId}`, { cache: "no-store" });
  if (!Array.isArray(rows)) throw new ApiError(502, "The server returned an invalid message list.");
  return rows.map((value) => {
    const row = value as Partial<ConversationMessage> | null;
    if (!row || !Number.isInteger(row.id) || (row.id ?? 0) <= 0 || row.conversation_id !== conversationId ||
        typeof row.role !== "string" || typeof row.content !== "string" || typeof row.created_at !== "string") {
      throw new ApiError(502, "The server returned invalid messages for this conversation.");
    }
    return row as ConversationMessage;
  });
}

export async function sendConversationMessage(conversationId: number, agentId: number, message: string): Promise<AgentChatResponse> {
  try {
    const reply = await requestJson<AgentChatResponse>(`/conversations/${conversationId}/chat?agent_id=${agentId}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: message.trim() }),
    });
    if (!reply || !Number.isInteger(reply.execution_id) || reply.execution_id <= 0 ||
        typeof reply.response !== "string" ||
        !["completed", "failed", "pending", "running", "cancelled"].includes(reply.status)) {
      throw new ApiError(502, "The server returned an invalid chat result. Reload messages before trying again.");
    }
    return reply;
  } catch (error) {
    if (error instanceof ApiError && error.status === 422) {
      throw new ApiError(422, "Enter a message of 1 to 4000 characters.");
    }
    throw error;
  }
}
