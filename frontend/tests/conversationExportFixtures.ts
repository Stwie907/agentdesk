export const exportConversation = { id: 91, agent_id: 7, title: '中文 "notes" /../', created_at: "2026-10-10T06:00:00" };
export const exportMessages = Array.from({ length: 25 }, (_, index) => ({
  id: index + 1, conversation_id: 91, role: index % 2 === 0 ? "user" : "assistant",
  content: `Saved turn ${index + 1} — 中文\n`, created_at: exportConversation.created_at,
}));
export function exportData() {
  return { schema_version: 1, conversation: { ...exportConversation }, message_count: 25, messages: exportMessages.map((row) => ({ ...row })) };
}
export function exportResponse(format: "json" | "markdown" = "json", body?: unknown, headers: Record<string, string> = {}): Response {
  const text = body === undefined ? (format === "json" ? JSON.stringify(exportData()) : "# Conversation 91\n\n中文 transcript\n") :
    (typeof body === "string" ? body : JSON.stringify(body));
  return new Response(text, { headers: {
    "Content-Type": format === "json" ? "application/json" : "text/markdown; charset=utf-8",
    "Content-Disposition": `attachment; filename="conversation-91.${format === "json" ? "json" : "md"}"`,
    "X-Conversation-ID": "91", "X-Agent-ID": "7", "X-Message-Count": "25", "X-Export-Schema-Version": "1", ...headers,
  } });
}
