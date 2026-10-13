import type { ConversationAttachment, ConversationExportFormat } from "./conversationExport";
import { ApiError } from "./executions";
import { validateMessageContext, type MessageContext } from "./messageContext";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";
const MAX_BYTES = 10 * 1024 * 1024;
const EXPORT_KIND = "agentdesk.message_context";

function literalBlock(value: string): string {
  let longest = 0;
  for (const match of value.matchAll(/`+/g)) longest = Math.max(longest, match[0].length);
  const fence = "`".repeat(Math.max(3, longest + 1));
  return `${fence}text\n${value}\n${fence}\n`;
}

function expectedMarkdown(context: MessageContext): string {
  let text = "# Saved message context\n\n" +
    "This is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n" +
    `- Export kind: ${EXPORT_KIND}\n- Export schema: 1\n` +
    `- Conversation ID: ${context.conversation_id}\n- Agent ID: ${context.agent_id}\n` +
    `- Selected message ID: ${context.anchor_message_id}\n` +
    `- Requested earlier messages: ${context.before}\n- Requested later messages: ${context.after}\n` +
    `- Selected message index: ${context.anchor_index}\n` +
    `- Earlier saved messages outside excerpt: ${context.has_more_before}\n` +
    `- Later saved messages outside excerpt: ${context.has_more_after}\n- Saved messages: ${context.items.length}\n`;
  for (const row of context.items) {
    const label = row.id === context.anchor_message_id ? "Selected message" : "Saved message";
    text += `\n## ${label} ${row.id}\n\nRole:\n\n${literalBlock(row.role)}` +
      `\nCreated at: ${row.created_at}\n\nContent:\n\n${literalBlock(row.content)}`;
  }
  return text;
}

function sameContext(expected: MessageContext, actual: MessageContext): boolean {
  return expected.anchor_index === actual.anchor_index && expected.has_more_before === actual.has_more_before &&
    expected.has_more_after === actual.has_more_after && expected.items.length === actual.items.length &&
    expected.items.every((row, index) => {
      const other = actual.items[index];
      return row.id === other.id && row.conversation_id === other.conversation_id && row.role === other.role &&
        row.content === other.content && row.created_at === other.created_at;
    });
}

export async function getMessageContextExport(
  context: MessageContext, format: ConversationExportFormat, signal?: AbortSignal,
): Promise<ConversationAttachment> {
  if (!context || typeof context !== "object" || (format !== "json" && format !== "markdown")) {
    throw new ApiError(422, "Load a saved message context and choose JSON or Markdown before exporting.");
  }
  const validated = validateMessageContext(context, context.conversation_id, context.agent_id,
    context.anchor_message_id, context.before, context.after);
  const expected = { ...validated, items: validated.items.map((row) => ({ ...row })) };
  const params = new URLSearchParams({ agent_id: String(expected.agent_id), before: String(expected.before),
    after: String(expected.after), format });
  const response = await fetch(`${API_BASE_URL}/conversations/${expected.conversation_id}/messages/${expected.anchor_message_id}/context/export?${params}`,
    { cache: "no-store", signal });
  if (!response.ok) {
    let message = `Unable to export message context (status ${response.status}).`;
    try {
      const body = await response.json() as { detail?: unknown };
      if (typeof body?.detail === "string") message = body.detail;
    } catch { /* Keep a stable error for non-JSON responses. */ }
    throw new ApiError(response.status, message);
  }
  const extension = format === "json" ? "json" : "md";
  const filename = `conversation-${expected.conversation_id}-message-${expected.anchor_message_id}-context.${extension}`;
  const mime = format === "json" ? "application/json" : "text/markdown";
  const countHeader = response.headers.get("X-Message-Count") ?? "";
  const messageCount = Number(countHeader);
  if (response.headers.get("X-Conversation-ID") !== String(expected.conversation_id) ||
      response.headers.get("X-Agent-ID") !== String(expected.agent_id) ||
      response.headers.get("X-Anchor-Message-ID") !== String(expected.anchor_message_id) ||
      response.headers.get("X-Context-Export-Kind") !== EXPORT_KIND ||
      response.headers.get("X-Context-Export-Schema-Version") !== "1" ||
      response.headers.get("Content-Disposition") !== `attachment; filename="${filename}"` ||
      response.headers.get("Content-Type")?.split(";")[0].trim() !== mime ||
      response.headers.get("Cache-Control") !== "no-store" || response.headers.get("X-Content-Type-Options") !== "nosniff" ||
      !/^[1-9]\d*$/.test(countHeader) || !Number.isSafeInteger(messageCount) || messageCount > expected.before + 1 + expected.after) {
    throw new ApiError(502, "The server returned invalid message context export metadata.");
  }
  const content = await response.arrayBuffer();
  if (content.byteLength === 0 || content.byteLength > MAX_BYTES) {
    throw new ApiError(502, "The server returned an empty or oversized message context export.");
  }
  let text: string;
  try { text = new TextDecoder("utf-8", { fatal: true }).decode(content); }
  catch { throw new ApiError(502, "The server returned an invalid UTF-8 message context export."); }
  let unchanged: boolean;
  if (format === "json") {
    let snapshot;
    try { snapshot = JSON.parse(text); }
    catch { throw new ApiError(502, "The server returned invalid message context export JSON."); }
    if (snapshot?.export_kind !== EXPORT_KIND || snapshot?.schema_version !== 1 || snapshot?.message_count !== messageCount) {
      throw new ApiError(502, "The server returned an invalid message context export schema.");
    }
    const actual = validateMessageContext(snapshot.context, expected.conversation_id, expected.agent_id,
      expected.anchor_message_id, expected.before, expected.after);
    if (actual.items.length !== messageCount) throw new ApiError(502, "The server returned an incomplete message context export.");
    unchanged = sameContext(expected, actual);
  } else {
    unchanged = messageCount === expected.items.length && text === expectedMarkdown(expected);
  }
  if (!unchanged) {
    throw new ApiError(409, "Saved messages changed since this context was loaded. Reload message context before exporting.");
  }
  return { blob: new Blob([content], { type: `${mime};charset=utf-8` }), filename, messageCount };
}
