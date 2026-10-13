import { asciiLower, type MessageRoleFilter } from "../src/api/messageSearch";
import type { ConversationMessage } from "../src/types/conversations";
import { exportMessages } from "./conversationExportFixtures";

export function messageSearchData(query = "中文", role: MessageRoleFilter = null, limit = 10, offset = 0, messages = exportMessages) {
  const normalized = query.trim();
  const rows = messages.filter((row) => asciiLower(row.content).includes(asciiLower(normalized)) && (role === null || row.role === role))
    .slice().reverse();
  return { conversation_id: 91, agent_id: 7, query: normalized, role, limit, offset, total: rows.length,
    has_more: offset + Math.min(limit, Math.max(0, rows.length - offset)) < rows.length,
    items: rows.slice(offset, offset + limit).map((row) => {
      const characters = [...row.content], folded = [...asciiLower(row.content)], count = [...normalized].length;
      const position = folded.findIndex((_, index) => folded.slice(index, index + count).join("") === asciiLower(normalized));
      let start = Math.max(0, position - Math.floor((240 - count) / 2));
      const end = Math.min(characters.length, start + 240); start = Math.max(0, end - 240);
      return { id: row.id, conversation_id: row.conversation_id, role: row.role, created_at: row.created_at,
        snippet: characters.slice(start, end).join(""), match_start: position - start, match_end: position - start + count,
        truncated_before: start > 0, truncated_after: end < characters.length };
    }) };
}

export function searchResponse(data: unknown = messageSearchData(), status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" } });
}

export function detailResponse(message: ConversationMessage = exportMessages[0], status = 200): Response {
  return searchResponse(message, status);
}
