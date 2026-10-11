import type { ConversationExportFormat } from "../src/api/conversationExport";
import type { MessageContext } from "../src/api/messageContext";
import { contextData } from "./messageContextFixtures";

// Captured from the backend serializer; keep literal Markdown contract fixtures.
export const contextMarkdownFixtures: Record<string, string> = {
  "1/3/3": "# Saved message context\n\nThis is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n- Export kind: agentdesk.message_context\n- Export schema: 1\n- Conversation ID: 91\n- Agent ID: 7\n- Selected message ID: 1\n- Requested earlier messages: 3\n- Requested later messages: 3\n- Selected message index: 0\n- Earlier saved messages outside excerpt: false\n- Later saved messages outside excerpt: true\n- Saved messages: 4\n\n## Selected message 1\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 1 — 中文\n\n```\n\n## Saved message 2\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 2 — 中文\n\n```\n\n## Saved message 3\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 3 — 中文\n\n```\n\n## Saved message 4\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 4 — 中文\n\n```\n",
  "25/3/3": "# Saved message context\n\nThis is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n- Export kind: agentdesk.message_context\n- Export schema: 1\n- Conversation ID: 91\n- Agent ID: 7\n- Selected message ID: 25\n- Requested earlier messages: 3\n- Requested later messages: 3\n- Selected message index: 3\n- Earlier saved messages outside excerpt: true\n- Later saved messages outside excerpt: false\n- Saved messages: 4\n\n## Saved message 22\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 22 — 中文\n\n```\n\n## Saved message 23\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 23 — 中文\n\n```\n\n## Saved message 24\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 24 — 中文\n\n```\n\n## Selected message 25\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 25 — 中文\n\n```\n",
  "13/3/3": "# Saved message context\n\nThis is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n- Export kind: agentdesk.message_context\n- Export schema: 1\n- Conversation ID: 91\n- Agent ID: 7\n- Selected message ID: 13\n- Requested earlier messages: 3\n- Requested later messages: 3\n- Selected message index: 3\n- Earlier saved messages outside excerpt: true\n- Later saved messages outside excerpt: true\n- Saved messages: 7\n\n## Saved message 10\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 10 — 中文\n\n```\n\n## Saved message 11\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 11 — 中文\n\n```\n\n## Saved message 12\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 12 — 中文\n\n```\n\n## Selected message 13\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 13 — 中文\n\n```\n\n## Saved message 14\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 14 — 中文\n\n```\n\n## Saved message 15\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 15 — 中文\n\n```\n\n## Saved message 16\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 16 — 中文\n\n```\n",
  "13/0/0": "# Saved message context\n\nThis is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n- Export kind: agentdesk.message_context\n- Export schema: 1\n- Conversation ID: 91\n- Agent ID: 7\n- Selected message ID: 13\n- Requested earlier messages: 0\n- Requested later messages: 0\n- Selected message index: 0\n- Earlier saved messages outside excerpt: true\n- Later saved messages outside excerpt: true\n- Saved messages: 1\n\n## Selected message 13\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 13 — 中文\n\n```\n",
  "13/10/10": "# Saved message context\n\nThis is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n- Export kind: agentdesk.message_context\n- Export schema: 1\n- Conversation ID: 91\n- Agent ID: 7\n- Selected message ID: 13\n- Requested earlier messages: 10\n- Requested later messages: 10\n- Selected message index: 10\n- Earlier saved messages outside excerpt: true\n- Later saved messages outside excerpt: true\n- Saved messages: 21\n\n## Saved message 3\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 3 — 中文\n\n```\n\n## Saved message 4\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 4 — 中文\n\n```\n\n## Saved message 5\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 5 — 中文\n\n```\n\n## Saved message 6\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 6 — 中文\n\n```\n\n## Saved message 7\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 7 — 中文\n\n```\n\n## Saved message 8\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 8 — 中文\n\n```\n\n## Saved message 9\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 9 — 中文\n\n```\n\n## Saved message 10\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 10 — 中文\n\n```\n\n## Saved message 11\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 11 — 中文\n\n```\n\n## Saved message 12\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 12 — 中文\n\n```\n\n## Selected message 13\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 13 — 中文\n\n```\n\n## Saved message 14\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 14 — 中文\n\n```\n\n## Saved message 15\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 15 — 中文\n\n```\n\n## Saved message 16\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 16 — 中文\n\n```\n\n## Saved message 17\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 17 — 中文\n\n```\n\n## Saved message 18\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 18 — 中文\n\n```\n\n## Saved message 19\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 19 — 中文\n\n```\n\n## Saved message 20\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 20 — 中文\n\n```\n\n## Saved message 21\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 21 — 中文\n\n```\n\n## Saved message 22\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 22 — 中文\n\n```\n\n## Saved message 23\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 23 — 中文\n\n```\n",
  "13/1/5": "# Saved message context\n\nThis is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n- Export kind: agentdesk.message_context\n- Export schema: 1\n- Conversation ID: 91\n- Agent ID: 7\n- Selected message ID: 13\n- Requested earlier messages: 1\n- Requested later messages: 5\n- Selected message index: 1\n- Earlier saved messages outside excerpt: true\n- Later saved messages outside excerpt: true\n- Saved messages: 7\n\n## Saved message 12\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 12 — 中文\n\n```\n\n## Selected message 13\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 13 — 中文\n\n```\n\n## Saved message 14\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 14 — 中文\n\n```\n\n## Saved message 15\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 15 — 中文\n\n```\n\n## Saved message 16\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 16 — 中文\n\n```\n\n## Saved message 17\n\nRole:\n\n```text\nuser\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 17 — 中文\n\n```\n\n## Saved message 18\n\nRole:\n\n```text\nassistant\n```\n\nCreated at: 2026-10-10T06:00:00\n\nContent:\n\n```text\nSaved turn 18 — 中文\n\n```\n",
  "13/1/1": "# Saved message context\n\nThis is a saved-message excerpt. Import conversation requires a full conversation JSON backup.\n\n- Export kind: agentdesk.message_context\n- Export schema: 1\n- Conversation ID: 91\n- Agent ID: 7\n- Selected message ID: 13\n- Requested earlier messages: 1\n- Requested later messages: 1\n- Selected message index: 1\n- Earlier saved messages outside excerpt: false\n- Later saved messages outside excerpt: false\n- Saved messages: 3\n\n## Saved message 900\n\nRole:\n\n```text\n\n```\n\nCreated at: 0001-01-01T00:00:00.000001\n\nContent:\n\n```text\n\n```\n\n## Selected message 13\n\nRole:\n\n````text\narchived/```custom\n````\n\nCreated at: 0001-01-01T00:00:00.000002\n\nContent:\n\n````````text\n🐍<script>alert(\"literal\")</script>\r\n```````markdown\n# literal heading\n```````\nTail:  \n\n````````\n\n## Saved message 1\n\nRole:\n\n```text\ntool\n```\n\nCreated at: 9999-12-31T23:59:59.999999\n\nContent:\n\n```text\nEnd:  \n\n```\n"
};

export function contextExportData(context: MessageContext = contextData()) {
  return { export_kind: "agentdesk.message_context", schema_version: 1, message_count: context.items.length, context };
}

export function contextExportResponse(
  format: ConversationExportFormat = "json", context: MessageContext = contextData(), body?: unknown,
  headers: Record<string, string> = {},
): Response {
  const text = body === undefined ? (format === "json" ? JSON.stringify(contextExportData(context)) :
    contextMarkdownFixtures[`${context.anchor_message_id}/${context.before}/${context.after}`]) :
    typeof body === "string" ? body : JSON.stringify(body);
  return new Response(text, { headers: {
    "Content-Type": format === "json" ? "application/json; charset=utf-8" : "text/markdown; charset=utf-8",
    "Content-Disposition": `attachment; filename="conversation-${context.conversation_id}-message-${context.anchor_message_id}-context.${format === "json" ? "json" : "md"}"`,
    "X-Conversation-ID": String(context.conversation_id), "X-Agent-ID": String(context.agent_id),
    "X-Anchor-Message-ID": String(context.anchor_message_id), "X-Message-Count": String(context.items.length),
    "X-Context-Export-Kind": "agentdesk.message_context", "X-Context-Export-Schema-Version": "1",
    "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", ...headers,
  } });
}

const literalContextFixtureData = {
  "conversation_id": 91,
  "agent_id": 7,
  "anchor_message_id": 13,
  "before": 1,
  "after": 1,
  "anchor_index": 1,
  "has_more_before": false,
  "has_more_after": false,
  "items": [
    {
      "id": 900,
      "conversation_id": 91,
      "role": "",
      "content": "",
      "created_at": "0001-01-01T00:00:00.000001"
    },
    {
      "id": 13,
      "conversation_id": 91,
      "role": "archived/```custom",
      "content": "🐍<script>alert(\"literal\")</script>\r\n```````markdown\n# literal heading\n```````\nTail:  \n",
      "created_at": "0001-01-01T00:00:00.000002"
    },
    {
      "id": 1,
      "conversation_id": 91,
      "role": "tool",
      "content": "End:  \n",
      "created_at": "9999-12-31T23:59:59.999999"
    }
  ]
};

export function literalContextFixture(): MessageContext {
  return { ...literalContextFixtureData, items: literalContextFixtureData.items.map((row) => ({ ...row })) };
}
