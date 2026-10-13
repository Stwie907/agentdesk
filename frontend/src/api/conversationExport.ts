import { ApiError } from "./executions";
import { compareConversationMessages } from "./conversations";
import type { ConversationMessage } from "../types/conversations";

export type ConversationExportFormat = "json" | "markdown";
export type ConversationAttachment = { blob: Blob; filename: string; messageCount: number };
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const MAX_BYTES = 10 * 1024 * 1024;

export async function getConversationExport(
  conversationId: number, agentId: number, format: ConversationExportFormat, signal?: AbortSignal,
): Promise<ConversationAttachment> {
  const params = new URLSearchParams({ agent_id: String(agentId), format });
  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/export?${params}`, { cache: "no-store", signal });
  if (!response.ok) {
    let message = `Unable to export conversation (status ${response.status}).`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body?.detail === "string") message = body.detail;
    } catch { /* Retain the stable error for non-JSON responses. */ }
    throw new ApiError(response.status, message);
  }
  const filename = `conversation-${conversationId}.${format === "json" ? "json" : "md"}`;
  const mime = format === "json" ? "application/json" : "text/markdown";
  const countHeader = response.headers.get("X-Message-Count") ?? "";
  const messageCount = Number(countHeader);
  if (response.headers.get("X-Conversation-ID") !== String(conversationId) ||
      response.headers.get("X-Agent-ID") !== String(agentId) || response.headers.get("X-Export-Schema-Version") !== "1" ||
      response.headers.get("Content-Disposition") !== `attachment; filename="${filename}"` ||
      response.headers.get("Content-Type")?.split(";")[0].trim() !== mime ||
      !/^\d+$/.test(countHeader) || !Number.isSafeInteger(messageCount) || messageCount > 10000) {
    throw new ApiError(502, "The server returned invalid export metadata for this conversation.");
  }
  const content = await response.arrayBuffer();
  if (content.byteLength === 0 || content.byteLength > MAX_BYTES) {
    throw new ApiError(502, "The server returned an empty or oversized conversation export.");
  }
  let text: string;
  try { text = new TextDecoder("utf-8", { fatal: true }).decode(content); }
  catch { throw new ApiError(502, "The server returned an invalid UTF-8 conversation export."); }
  if (format === "json") {
    let data;
    try { data = JSON.parse(text); }
    catch { throw new ApiError(502, "The server returned invalid conversation export JSON."); }
    const conversation = data?.conversation;
    if (data?.schema_version !== 1 || data?.message_count !== messageCount || conversation?.id !== conversationId ||
        conversation?.agent_id !== agentId || !(typeof conversation?.title === "string" || conversation?.title === null) ||
        typeof conversation?.created_at !== "string" || !Number.isFinite(Date.parse(conversation.created_at)) ||
        !Array.isArray(data?.messages) || data.messages.length !== messageCount) {
      throw new ApiError(502, "The server returned an incomplete or foreign conversation export.");
    }
    const ids = new Set<number>();
    let previous: ConversationMessage | null = null;
    for (const row of data.messages) {
      if (!row || !Number.isSafeInteger(row.id) || row.id <= 0 || ids.has(row.id) || row.conversation_id !== conversationId ||
          typeof row.role !== "string" || typeof row.content !== "string" || typeof row.created_at !== "string") {
        throw new ApiError(502, "The server returned invalid or foreign export messages.");
      }
      compareConversationMessages(row, row);
      if (previous && compareConversationMessages(previous, row) >= 0) {
        throw new ApiError(502, "The server returned incorrectly ordered export messages.");
      }
      ids.add(row.id);
      previous = row;
    }
  }
  return { blob: new Blob([content], { type: `${mime};charset=utf-8` }), filename, messageCount };
}

export function downloadConversationAttachment(attachment: ConversationAttachment): void {
  const url = URL.createObjectURL(attachment.blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = attachment.filename;
  try { document.body.append(link); link.click(); }
  finally {
    link.remove();
    // Keep the URL alive briefly for the browser to begin reading the download.
    window.setTimeout(URL.revokeObjectURL.bind(URL, url), 1000);
  }
}
